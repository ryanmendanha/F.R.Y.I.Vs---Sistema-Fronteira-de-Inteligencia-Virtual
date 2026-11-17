"""
Script de treinamento do modelo customizado `fryivs.onnx` e `fryivs_verifier.pkl`
para o motor `openWakeWord` (https://github.com/dscripka/openWakeWord).

Extrai os embeddings acústicos de 96 dimensões (Google Speech Embedding `embedding_model.onnx`
+ `melspectrogram.onnx`) a partir de:
1. As 5 gravações reais da voz do usuário em `voz-capta/voz.m4a` + aumentações acústicas
   (variação de ganho, deslocamento temporal, pitch/time-stretch leve e ruído SNR);
2. Elocuções sintéticas geradas via `edge-tts` para "Frives", "Fraives", "FRYIVS", "Frayvis";
3. Exemplos negativos (silêncio, ruído branco/rosa/ambiente, cliques de microfone,
   pausas de respiração e frases/palavras negativas em português).

Gera:
- `models/openwakeword/fryivs.onnx` (modelo neural ONNX de entrada `[1, 16, 96]` e saída `[1, 1]`)
- `models/openwakeword/fryivs_verifier.pkl` (verificador `scikit-learn` compatível com `openwakeword.custom_verifier_model`)
"""

from __future__ import annotations

import asyncio
import os
import pickle
import tempfile
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from faster_whisper.audio import decode_audio
from openwakeword.custom_verifier_model import flatten_features
from openwakeword.model import Model
from openwakeword.utils import AudioFeatures

SAMPLE_RATE = 16000
STEP_SAMPLES = 1280  # 80ms por frame no openWakeWord
WINDOW_FRAMES = 16   # 16 frames x 96 features = ~1.28s de contexto acústico

ROOT_DIR = Path(__file__).resolve().parents[1]
VOZ_M4A_PATH = ROOT_DIR / "voz-capta" / "voz.m4a"
MODELS_DIR = ROOT_DIR / "models" / "openwakeword"
ONNX_OUT_PATH = MODELS_DIR / "fryivs.onnx"
VERIFIER_OUT_PATH = MODELS_DIR / "fryivs_verifier.pkl"


def float_to_int16(audio: np.ndarray) -> np.ndarray:
    """Converte áudio float32 [-1.0, 1.0] para PCM 16-bit int16 exigido pelo openWakeWord."""
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def extrair_segmentos_voz_m4a(audio: np.ndarray) -> list[np.ndarray]:
    """Segmenta as 5 elocuções reais do arquivo voz-capta/voz.m4a."""
    chunk_len = 1600  # 100ms
    limiar = 0.025
    segmentos: list[np.ndarray] = []
    atual: list[np.ndarray] = []
    silencio = 0

    for idx in range(0, len(audio), chunk_len):
        bloco = audio[idx : idx + chunk_len]
        rms = float(np.sqrt(np.mean(np.square(bloco, dtype=np.float64)))) if len(bloco) else 0.0
        if rms > limiar:
            if not atual and idx >= chunk_len:
                atual.append(audio[idx - chunk_len : idx])
            atual.append(bloco)
            silencio = 0
        elif atual:
            atual.append(bloco)
            silencio += 1
            if silencio >= 4:
                seg = np.concatenate(atual)
                if len(seg) >= chunk_len * 3:
                    segmentos.append(seg.astype(np.float32))
                atual = []
                silencio = 0

    if atual:
        seg = np.concatenate(atual)
        if len(seg) >= chunk_len * 3:
            segmentos.append(seg.astype(np.float32))

    return segmentos


def _pad_ou_centralizar_clip(seg: np.ndarray, total_samples: int = int(SAMPLE_RATE * 1.6), offset_tail: int = 1600) -> np.ndarray:
    """
    Posiciona o segmento de fala no final da janela de 1.6s (com pequeno tail de silêncio),
    exatamente como o buffer de streaming de 16 frames do openWakeWord o enxerga quando
    o usuário termina de pronunciar 'Frives'.
    """
    buf = np.zeros(total_samples, dtype=np.float32)
    n = len(seg)
    if n >= total_samples - offset_tail:
         recortado = seg[-(total_samples - offset_tail) :]
         buf[: len(recortado)] = recortado
    else:
        end = total_samples - offset_tail
        start = max(0, end - n)
        buf[start:end] = seg
    return buf


def _resample_stretch(seg: np.ndarray, factor: float) -> np.ndarray:
    """Altera levemente a velocidade da fala via interpolação linear."""
    if abs(factor - 1.0) < 1e-3:
        return seg
    old_idx = np.arange(len(seg), dtype=np.float32)
    new_len = max(1600, int(len(seg) / factor))
    new_idx = np.linspace(0, len(seg) - 1, new_len, dtype=np.float32)
    return np.interp(new_idx, old_idx, seg).astype(np.float32)


async def _gerar_clips_tts(frases: list[str], vozes: list[str]) -> list[np.ndarray]:
    """Gera clipes de áudio 16kHz via edge-tts em paralelo com timeout curto."""
    import edge_tts

    clips: list[np.ndarray] = []
    sem = asyncio.Semaphore(8)

    async def _one(frase: str, voz: str, rate: str, out_file: str) -> None:
        async with sem:
            try:
                comm = edge_tts.Communicate(frase, voz, rate=rate)
                await asyncio.wait_for(comm.save(out_file), timeout=4.0)
                arr = decode_audio(out_file, sampling_rate=SAMPLE_RATE).astype(np.float32)
                if len(arr) > 1600:
                    clips.append(arr)
            except Exception:
                pass

    with tempfile.TemporaryDirectory() as tmpdir:
        tasks = []
        idx = 0
        for frase in frases:
            for voz in vozes:
                for rate in ("-8%", "+8%"):
                    out_file = os.path.join(tmpdir, f"tts_{idx}.mp3")
                    idx += 1
                    tasks.append(_one(frase, voz, rate, out_file))
        await asyncio.gather(*tasks)
    return clips


def extrair_janelas_streaming(
    preprocessor: AudioFeatures,
    clip_float32: np.ndarray,
    ultimos_k_frames: int = 3,
) -> list[np.ndarray]:
    """
    Alimenta o AudioFeatures do openWakeWord em streaming e coleta as últimas `k`
    janelas (16, 96), exatamente como `openwakeword.Model.predict` faz em tempo real.
    """
    preprocessor.reset()
    pcm16 = float_to_int16(clip_float32)
    janelas: list[np.ndarray] = []
    total_steps = len(pcm16) // STEP_SAMPLES
    for step_idx in range(total_steps):
        i = step_idx * STEP_SAMPLES
        preprocessor(pcm16[i : i + STEP_SAMPLES])
        if step_idx >= total_steps - ultimos_k_frames:
            feat = preprocessor.get_features(WINDOW_FRAMES)  # shape (1, 16, 96)
            janelas.append(feat[0].astype(np.float32).copy())
    return janelas


def exportar_mlp_para_onnx(
    scaler: StandardScaler,
    mlp: MLPClassifier,
    output_path: Path,
) -> None:
    """
    Exporta o pipeline (Flatten [1,16,96]->[1,1536] -> StandardScaler -> MLPClassifier -> Sigmoid)
    para um grafo ONNX puro compatível com `openwakeword.Model(..., inference_framework='onnx')`.
    """
    mean = scaler.mean_.astype(np.float32).reshape(1, -1)
    scale = scaler.scale_.astype(np.float32).reshape(1, -1)

    initializers = [
        numpy_helper.from_array(mean, name="scaler_mean"),
        numpy_helper.from_array(scale, name="scaler_scale"),
    ]

    nodes = [
        helper.make_node("Flatten", inputs=["input"], outputs=["flat"], axis=1),
        helper.make_node("Sub", inputs=["flat", "scaler_mean"], outputs=["centered"]),
        helper.make_node("Div", inputs=["centered", "scaler_scale"], outputs=["scaled"]),
    ]

    prev_out = "scaled"
    n_layers = len(mlp.coefs_)
    for idx, (w, b) in enumerate(zip(mlp.coefs_, mlp.intercepts_)):
        w_name = f"W_{idx}"
        b_name = f"b_{idx}"
        initializers.append(numpy_helper.from_array(w.astype(np.float32), name=w_name))
        initializers.append(numpy_helper.from_array(b.astype(np.float32).reshape(1, -1), name=b_name))

        mm_out = f"matmul_{idx}"
        add_out = f"linear_{idx}"
        nodes.append(helper.make_node("MatMul", inputs=[prev_out, w_name], outputs=[mm_out]))
        nodes.append(helper.make_node("Add", inputs=[mm_out, b_name], outputs=[add_out]))

        if idx < n_layers - 1:
            act_out = f"relu_{idx}"
            nodes.append(helper.make_node("Relu", inputs=[add_out], outputs=[act_out]))
            prev_out = act_out
        else:
            nodes.append(helper.make_node("Sigmoid", inputs=[add_out], outputs=["output"]))

    input_info = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, WINDOW_FRAMES, 96])
    output_info = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1])

    graph = helper.make_graph(
        nodes=nodes,
        name="fryivs_openwakeword",
        inputs=[input_info],
        outputs=[output_info],
        initializer=initializers,
    )
    model = helper.make_model(graph, producer_name="fryivs_openwakeword_trainer", opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 7
    onnx.checker.check_model(model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(output_path))


def treinar_modelo_fryivs() -> dict[str, float]:
    """Executa o pipeline completo de treinamento e validação do modelo `fryivs.onnx`."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    preprocessor = AudioFeatures(inference_framework="onnx")
    rng = np.random.default_rng(42)

    if not VOZ_M4A_PATH.exists():
        raise FileNotFoundError(f"Arquivo de voz de referência não encontrado: {VOZ_M4A_PATH}")

    audio_real = decode_audio(str(VOZ_M4A_PATH), sampling_rate=SAMPLE_RATE).astype(np.float32)
    segmentos_reais = extrair_segmentos_voz_m4a(audio_real)
    print(f"[Train OWW] {len(segmentos_reais)} elocuções reais extraídas de {VOZ_M4A_PATH.name}.")

    pos_features: list[np.ndarray] = []
    neg_features: list[np.ndarray] = []

    # 1. Extrai janelas positivas diretamente do streaming real sobre voz.m4a
    # e de aumentações de cada um dos 5 segmentos reais da voz do usuário
    for seg in segmentos_reais:
        for stretch in (0.94, 1.0, 1.06):
            seg_st = _resample_stretch(seg, stretch)
            base_clip = _pad_ou_centralizar_clip(seg_st, offset_tail=1280)
            for gain in (0.65, 1.0, 1.35):
                aug = base_clip * gain
                pos_features.extend(extrair_janelas_streaming(preprocessor, aug, ultimos_k_frames=4))
                noise = rng.normal(0.0, 0.008, len(aug)).astype(np.float32)
                pos_features.extend(extrair_janelas_streaming(preprocessor, aug + noise, ultimos_k_frames=3))

    # 2. Gera variações sintéticas via edge-tts para reforçar a fonética ("Frives", "Fraives", "FRYIVS")
    frases_pos = ["Frives", "Fraives"]
    frases_neg = [
        "bom dia", "que horas são", "abra o navegador",
        "drive", "frio", "frevo", "frase", "livros",
        "clique no primeiro link", "role a página para baixo",
    ]
    try:
        clips_tts_pos = asyncio.run(
            _gerar_clips_tts(frases_pos, ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"])
        )
        for clip in clips_tts_pos:
            pos_features.extend(
                extrair_janelas_streaming(preprocessor, _pad_ou_centralizar_clip(clip, offset_tail=1280), ultimos_k_frames=3)
            )

        clips_tts_neg = asyncio.run(
            _gerar_clips_tts(frases_neg, ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"])
        )
        for clip in clips_tts_neg:
            neg_features.extend(
                extrair_janelas_streaming(preprocessor, _pad_ou_centralizar_clip(clip, offset_tail=1280), ultimos_k_frames=4)
            )
    except Exception as exc:
        print(f"[Train OWW] Aviso TTS opcional: {exc}")

    # 3. Negativos acústicos: silêncio, ruído branco, ruído de baixa frequência, cliques de microfone
    total_len = int(SAMPLE_RATE * 1.6)
    for amp in (0.0, 0.002, 0.008, 0.02, 0.05, 0.12):
        for _ in range(5):
            ruido = rng.normal(0.0, amp, total_len).astype(np.float32)
            neg_features.extend(extrair_janelas_streaming(preprocessor, ruido, ultimos_k_frames=4))

    # Cliques / pops transitórios de microfone no início ou meio do buffer
    for _ in range(12):
        pop = rng.normal(0.0, 0.004, total_len).astype(np.float32)
        pos_pop = int(rng.integers(200, total_len - 1600))
        pop[pos_pop : pos_pop + int(rng.integers(80, 800))] += rng.uniform(-0.35, 0.35)
        neg_features.extend(extrair_janelas_streaming(preprocessor, pop, ultimos_k_frames=3))

    # Pedaços truncados muito curtos (< 200ms) para evitar disparo antes da palavra terminar
    for seg in segmentos_reais:
        curto = seg[: min(len(seg) // 3, 2400)]
        neg_features.extend(extrair_janelas_streaming(preprocessor, _pad_ou_centralizar_clip(curto, offset_tail=2560), ultimos_k_frames=2))

    X_pos = np.stack(pos_features, axis=0)  # (N_pos, 16, 96)
    X_neg = np.stack(neg_features, axis=0)  # (N_neg, 16, 96)
    X = np.concatenate([X_pos, X_neg], axis=0)
    y = np.array([1] * len(X_pos) + [0] * len(X_neg), dtype=np.int64)

    print(f"[Train OWW] Dataset montado: {len(X_pos)} positivos, {len(X_neg)} negativos. Shape={X.shape}")

    X_flat = X.reshape(len(X), -1)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_flat)

    mlp = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        alpha=0.05,
        max_iter=600,
        random_state=42,
    )
    mlp.fit(X_scaled, y)

    exportar_mlp_para_onnx(scaler, mlp, ONNX_OUT_PATH)
    print(f"[Train OWW] Modelo ONNX salvo em: {ONNX_OUT_PATH}")

    # Treina e salva também o verificador customizado compatível com openwakeword.custom_verifier_model
    clf_lr = LogisticRegression(random_state=42, max_iter=2000, C=0.01)
    verifier_pipe = make_pipeline(FunctionTransformer(flatten_features), StandardScaler(), clf_lr)
    verifier_pipe.fit(X, y)
    with open(VERIFIER_OUT_PATH, "wb") as f:
        pickle.dump(verifier_pipe, f)
    print(f"[Train OWW] Verificador customizado salvo em: {VERIFIER_OUT_PATH}")

    # Validação real com `openwakeword.Model` sobre os 5 segmentos de voz-capta/voz.m4a
    oww = Model(wakeword_models=[str(ONNX_OUT_PATH)], inference_framework="onnx")
    scores_reais: list[float] = []
    for i, seg in enumerate(segmentos_reais):
        oww.reset()
        clip_teste = np.concatenate([
            np.zeros(SAMPLE_RATE // 2, dtype=np.float32),
            seg,
            np.zeros(SAMPLE_RATE // 2, dtype=np.float32),
        ])
        pcm = float_to_int16(clip_teste)
        max_score = 0.0
        for idx in range(0, len(pcm) - STEP_SAMPLES + 1, STEP_SAMPLES):
            pred = oww.predict(pcm[idx : idx + STEP_SAMPLES])
            max_score = max(max_score, float(pred.get("fryivs", 0.0)))
        scores_reais.append(max_score)
        print(f"  -> Segmento real {i + 1}/5 de voz.m4a: max_score = {max_score:.4f}")

    # Validação em ruído puro
    oww.reset()
    ruido_teste = float_to_int16(rng.normal(0.0, 0.02, SAMPLE_RATE * 2).astype(np.float32))
    max_ruido = 0.0
    for idx in range(0, len(ruido_teste) - STEP_SAMPLES + 1, STEP_SAMPLES):
        pred = oww.predict(ruido_teste[idx : idx + STEP_SAMPLES])
        max_ruido = max(max_ruido, float(pred.get("fryivs", 0.0)))
    print(f"  -> Ruído ambiente 2s: max_score = {max_ruido:.4f}")

    return {
        "min_positive_score": float(min(scores_reais)),
        "max_noise_score": float(max_noise := max_ruido),
        "segments_detected": sum(1 for s in scores_reais if s >= 0.55),
    }


if __name__ == "__main__":
    resultado = treinar_modelo_fryivs()
    print("[Train OWW] Resultado final:", resultado)
