"""
Módulo de Speech-to-Text para F.R.Y.I.Vs.
Implementa gravação adaptativa com VAD (Voice Activity Detection) para máxima
responsividade: para de gravar assim que o usuário termina de falar, sem esperar
um tempo fixo. Usa faster-whisper com modelo 'small' para alta precisão
em português brasileiro, e suporta modelo 'base' dedicado para wake-word rápida.
"""

import os
from dotenv import load_dotenv
load_dotenv()
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from typing import Tuple
import numpy as np

# ── Configurações de gravação ────────────────────────────────────────────────
SAMPLE_RATE: int = 16000          # Hz requerido pelo Whisper
VAD_SILENCE_THRESHOLD: float = 0.02   # Limiar RMS de silêncio (mais alto = ignora mais ruído)
VAD_SILENCE_DURATION: float = 0.65    # Segundos de silêncio contínuo p/ parar (evita corte prematuro de pausas na fala)
VAD_MIN_DURATION: float = 0.8         # Duração mínima de captura
VAD_MAX_DURATION: float = 15.0        # Limite de segurança máximo em segundos
CHUNK_SIZE: int = 1600                # Amostras por chunk (~100ms a 16kHz)

# Prompt inicial neutro em português (NÃO incluir o nome/wake-word aqui para evitar
# que o Whisper alucine "Frives/FRYIVS" ao receber ruído de fundo ou clique de microfone).
WHISPER_INITIAL_PROMPT = (
    "Comandos de voz em português brasileiro para automação de computador, "
    "planilhas Excel, documentos Word e navegação na internet."
)


def eh_alucinacao_whisper(texto: str) -> bool:
    """
    Detecta alucinações clássicas do Whisper causadas por ruído de fundo, eco de caixa de som,
    silêncio ou clique de microfone:
    1. Repetição do próprio WHISPER_INITIAL_PROMPT ou WAKE_PROMPT.
    2. Loops de repetição de tokens (ex.: 'genios genios genios...', 'frives fraives frives...').
    3. Frases de encerramento de legenda do YouTube ('Obrigado por assistir', 'Legendas pela comunidade').
    """
    if not texto or not texto.strip():
        return True
    import re
    import unicodedata

    t_norm = "".join(
        c for c in unicodedata.normalize("NFKD", texto.strip().lower())
        if not unicodedata.combining(c)
    )
    t_clean = re.sub(r"[^a-z0-9\s]", " ", t_norm)
    tokens = [w for w in t_clean.split() if w]
    if not tokens:
        return True

    joined = " ".join(tokens)

    # 1. Vazamento do initial_prompt do Whisper ou de legendas de treinamento
    frases_alucinadas = (
        "comandos de voz em portugues brasileiro para automacao",
        "planilhas excel documentos word e navegacao na internet",
        "frives fryivs fraives",
        "frives frives fraives",
        "frives fraives frives",
        "frives frives",
        "fraives fraives",
        "fryivs fryivs",
        "obrigado por assistir",
        "inscreva se no canal",
        "legendas pela comunidade",
        "amara org",
        "subtitles by",
    )
    if any(f in joined for f in frases_alucinadas):
        return True

    # 2. Loop de repetição da mesma palavra >= 3 vezes seguidas (ex: 'genios genios genios')
    streak = 1
    for i in range(1, len(tokens)):
        if tokens[i] == tokens[i - 1]:
            streak += 1
            if streak >= 3:
                return True
        else:
            streak = 1

    # 3. Baixíssima diversidade vocabular em frases médias/longas (ex: 'frives fraives frives fraives...')
    if len(tokens) >= 5:
        unicos = set(tokens)
        if len(unicos) <= 2:
            return True
        # Se uma única palavra domina mais de 60% dos tokens numa frase de >= 5 palavras
        from collections import Counter
        mais_comum, qtd = Counter(tokens).most_common(1)[0]
        if qtd >= 4 and (qtd / len(tokens)) >= 0.60:
            return True

    return False

# ── Singletons do modelo Whisper ─────────────────────────────────────────────
import threading as _threading
_whisper_model = None
_whisper_models: dict[str, object] = {}
_whisper_lock = _threading.Lock()  # evita instanciação concorrente (double-checked locking)


def _get_whisper_model(model_name: str | None = None):
    """Carrega o modelo Whisper sob demanda e o mantém em cache (singleton thread-safe)."""
    global _whisper_model
    resolved = (model_name or os.getenv("WHISPER_MODEL", "small")).strip() or "small"
    default_name = (os.getenv("WHISPER_MODEL", "small").strip() or "small")

    # Fast-path sem lock (leitura de cache já preenchido)
    if model_name is None and _whisper_model is not None:
        return _whisper_model
    if model_name is not None and resolved in _whisper_models:
        return _whisper_models[resolved]

    with _whisper_lock:
        # Double-checked: outra thread pode ter preenchido enquanto esperávamos
        if model_name is None and _whisper_model is not None:
            return _whisper_model
        if model_name is not None and resolved in _whisper_models:
            return _whisper_models[resolved]

        from faster_whisper import WhisperModel
        threads = min(os.cpu_count() or 4, 8)
        print(f"[STT] Carregando modelo Whisper '{resolved}' (int8, threads={threads})...")
        instance = WhisperModel(
            resolved,
            device="cpu",
            compute_type="int8",
            cpu_threads=threads,
            num_workers=1
        )
        print(f"[STT] Modelo Whisper '{resolved}' pronto.")
        _whisper_models[resolved] = instance
        if model_name is None or resolved == default_name:
            _whisper_model = instance
        return instance


def _rms(chunk: np.ndarray) -> float:
    """Calcula o Root Mean Square (energia) de um chunk de áudio."""
    return float(np.sqrt(np.mean(chunk ** 2)))


def _trim_silence(audio: np.ndarray, fs: int, threshold: float = 0.01) -> np.ndarray:
    """Remove silêncio do início e fim do áudio para transcrição mais limpa."""
    chunk_len = int(fs * 0.05)  # chunks de 50ms para análise
    if len(audio) < chunk_len:
        return audio

    # Encontra o início da fala
    start = 0
    for i in range(0, len(audio) - chunk_len, chunk_len):
        if _rms(audio[i:i + chunk_len]) > threshold:
            start = max(0, i - chunk_len)  # mantém 50ms antes da fala
            break

    # Encontra o fim da fala
    end = len(audio)
    for i in range(len(audio) - chunk_len, start, -chunk_len):
        if _rms(audio[i:i + chunk_len]) > threshold:
            end = min(len(audio), i + chunk_len * 5)  # mantém ~250ms após a fala para preservar finais de palavras
            break

    trimmed = audio[start:end]
    if len(trimmed) < fs * 0.3:  # mínimo 300ms de áudio
        return audio
    return trimmed


def gravar_audio(duracao: int = 5, fs: int = SAMPLE_RATE) -> Tuple[np.ndarray, int]:
    """
    Grava áudio do microfone com VAD adaptativo.

    O parâmetro 'duracao' serve como fallback máximo de segurança.
    Na prática a gravação para automaticamente após silêncio
    detectado, tornando a captura muito mais responsiva.

    Returns:
        Tuple (audio_array_float32, sample_rate)
    """
    try:
        # Se o VoiceDaemon estiver ativo com o microfone aberto, delega para ele
        # para evitar conflito de stream exclusivo no Windows.
        try:
            from core import voice_daemon
            if voice_daemon.ativo() and voice_daemon.stream_aberto():
                return voice_daemon.capturar_audio_do_buffer(duracao=duracao, fs=fs)
        except Exception:
            pass

        import sounddevice as sd

        max_duration = min(float(duracao), VAD_MAX_DURATION)
        print(f"[STT] Ouvindo com VAD (max {max_duration:.0f}s)...")

        collected_chunks: list[np.ndarray] = []
        silence_chunks: int = 0
        elapsed_chunks: int = 0
        chunks_per_second = fs / CHUNK_SIZE
        min_chunks = int(VAD_MIN_DURATION * chunks_per_second)
        silence_limit = int(VAD_SILENCE_DURATION * chunks_per_second)
        max_chunks = int(max_duration * chunks_per_second)

        speech_started = False  # Flag para ignorar silêncio inicial

        with sd.InputStream(samplerate=fs, channels=1, dtype="float32",
                            blocksize=CHUNK_SIZE) as stream:
            while elapsed_chunks < max_chunks:
                chunk, _ = stream.read(CHUNK_SIZE)
                flat = chunk.flatten()
                collected_chunks.append(flat)
                elapsed_chunks += 1

                energy = _rms(flat)

                if energy > VAD_SILENCE_THRESHOLD:
                    speech_started = True
                    silence_chunks = 0  # reset contador de silêncio
                elif speech_started:
                    silence_chunks += 1

                # Para assim que detectar silêncio pós-fala (E respeitou o mínimo)
                if (speech_started
                        and silence_chunks >= silence_limit
                        and elapsed_chunks >= min_chunks):
                    print(f"[STT] Fala detectada e silencio confirmado "
                          f"({elapsed_chunks / chunks_per_second:.1f}s capturados).")
                    break

        if not collected_chunks:
            return np.array([], dtype="float32"), fs

        audio = np.concatenate(collected_chunks)

        # Remove silêncio desnecessário do início/fim para transcrição mais precisa
        audio = _trim_silence(audio, fs, threshold=VAD_SILENCE_THRESHOLD * 0.8)

        duration_sec = len(audio) / fs
        print(f"[STT] Audio capturado: {duration_sec:.1f}s ({len(audio)} amostras)")
        return audio, fs

    except Exception as e:
        print(f"[STT] Erro ao gravar audio: {e}")
        return np.array([], dtype="float32"), fs


def transcrever(
    audio_data: np.ndarray,
    fs: int = SAMPLE_RATE,
    language: str = "pt",
    model_name: str | None = None,
    initial_prompt: str | None = None,
    vad_filter: bool = True,
) -> str:
    """
    Transcreve um array numpy de áudio para texto usando Whisper.

    Args:
        audio_data: Array float32 com amostras de áudio
        fs: Taxa de amostragem (deve ser 16000 para Whisper)
        language: Código de idioma (padrão 'pt' para português)
        model_name: Modelo específico (ex.: 'base' para wake word) ou None p/ padrão
        initial_prompt: Prompt inicial customizado ou None p/ WHISPER_INITIAL_PROMPT
        vad_filter: Se deve aplicar VAD interno do faster-whisper

    Returns:
        Texto transcrito (str vazia em caso de erro ou silêncio)
    """
    try:
        if isinstance(audio_data, np.ndarray) and len(audio_data) == 0:
            return ""

        # Normaliza o áudio para [-1.0, 1.0] se necessário
        max_val = np.max(np.abs(audio_data))
        if max_val > 1.0:
            audio_data = audio_data / max_val

        model = _get_whisper_model() if model_name is None else _get_whisper_model(model_name)
        prompt_to_use = WHISPER_INITIAL_PROMPT if initial_prompt is None else initial_prompt

        segments_raw, info = model.transcribe(
            audio_data,
            language=language,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=200,
            ),
            initial_prompt=prompt_to_use,
            condition_on_previous_text=False,
            no_speech_threshold=0.55,
            log_prob_threshold=-1.0,
        )

        partes_validas: list[str] = []
        for s in segments_raw:
            txt = (s.text or "").strip()
            if not txt:
                continue
            no_speech = getattr(s, "no_speech_prob", None)
            avg_logprob = getattr(s, "avg_logprob", None)
            comp_ratio = getattr(s, "compression_ratio", None)
            if isinstance(no_speech, (int, float)) and no_speech > 0.45:
                continue
            if isinstance(avg_logprob, (int, float)) and avg_logprob < -1.10:
                continue
            if isinstance(comp_ratio, (int, float)) and comp_ratio > 2.4:
                continue
            if eh_alucinacao_whisper(txt):
                print(f"[STT] Alucinação descartada no segmento: '{txt[:60]}'")
                continue
            partes_validas.append(txt)

        resultado = " ".join(partes_validas).strip()
        if resultado and eh_alucinacao_whisper(resultado):
            print(f"[STT] Alucinação descartada no resultado final: '{resultado[:60]}'")
            resultado = ""

        if resultado:
            if info is not None:
                lang = getattr(info, "language", "pt")
                prob = getattr(info, "language_probability", 1.0)
                print(f"[STT] Transcrito: '{resultado}' (lang={lang}, prob={prob:.2f})")
            else:
                print(f"[STT] Transcrito: '{resultado}'")
        else:
            print("[STT] Nenhuma fala identificada no audio.")

        return resultado

    except Exception as e:
        print(f"[STT] Erro na transcricao: {e}")
        return ""
