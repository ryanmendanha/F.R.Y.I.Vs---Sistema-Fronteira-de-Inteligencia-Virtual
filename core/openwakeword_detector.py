"""
Integração oficial do motor `openWakeWord` (https://github.com/dscripka/openWakeWord)
para detecção acústica em tempo real da wake word "FRYIVS / Fraives / Frives".

Opera 100% via ONNX Runtime (`inference_framework="onnx"`):
- `melspectrogram.onnx` (extrator de espectrograma Mel a 16kHz)
- `embedding_model.onnx` (Google Speech Embedding de 96 dimensões)
- `silero_vad.onnx` (detector neural de atividade de voz Silero)
- `models/openwakeword/fryivs.onnx` (classificador neural customizado para a voz do usuário)
- `models/openwakeword/fryivs_verifier.pkl` (verificador de locutor do `openWakeWord`)
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any, Final

import numpy as np

ROOT_DIR: Final[Path] = Path(__file__).resolve().parents[1]
MODELS_DIR: Final[Path] = ROOT_DIR / "models" / "openwakeword"
FRYIVS_ONNX_PATH: Final[Path] = MODELS_DIR / "fryivs.onnx"
FRYIVS_VERIFIER_PATH: Final[Path] = MODELS_DIR / "fryivs_verifier.pkl"

OWW_STEP_SAMPLES: Final[int] = 1280
DEFAULT_OWW_THRESHOLD: Final[float] = 0.55
DEFAULT_VAD_THRESHOLD: Final[float] = 0.40


def _limiar_oww() -> float:
    try:
        return float(os.getenv("OPENWAKEWORD_THRESHOLD", DEFAULT_OWW_THRESHOLD))
    except ValueError:
        return DEFAULT_OWW_THRESHOLD


def _limiar_vad() -> float:
    try:
        return float(os.getenv("OPENWAKEWORD_VAD_THRESHOLD", DEFAULT_VAD_THRESHOLD))
    except ValueError:
        return DEFAULT_VAD_THRESHOLD


def float32_to_pcm16(audio: np.ndarray) -> np.ndarray:
    """Converte amostras float32 [-1.0, 1.0] para PCM 16-bit int16 exigido pelo openWakeWord."""
    if audio.dtype == np.int16:
        return audio
    arr = np.asarray(audio, dtype=np.float32).flatten()
    if len(arr) == 0:
        return np.array([], dtype=np.int16)
    max_abs = float(np.max(np.abs(arr)))
    if max_abs > 1.0:
        arr = arr / max_abs
    return (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)


def garantir_modelos_openwakeword() -> bool:
    """
    Garante que os modelos base ONNX do `openWakeWord` e o modelo customizado `fryivs.onnx`
    estejam disponíveis localmente antes de iniciar a escuta.
    """
    try:
        import openwakeword
        from openwakeword.utils import download_models

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        res_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        res_dir.mkdir(parents=True, exist_ok=True)

        base_files = ("melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx")
        for fname in base_files:
            src_local = MODELS_DIR / fname
            dst_pkg = res_dir / fname
            if src_local.exists() and not dst_pkg.exists():
                shutil.copy2(src_local, dst_pkg)
            elif dst_pkg.exists() and not src_local.exists():
                shutil.copy2(dst_pkg, src_local)

        if not all((res_dir / f).exists() for f in base_files):
            download_models(model_names=["alexa"], target_directory=str(MODELS_DIR))
            for fname in base_files:
                if (MODELS_DIR / fname).exists():
                    shutil.copy2(MODELS_DIR / fname, res_dir / fname)

        if not FRYIVS_ONNX_PATH.exists():
            from scripts.train_fryivs_openwakeword import treinar_modelo_fryivs

            treinar_modelo_fryivs()

        return FRYIVS_ONNX_PATH.exists()
    except Exception as exc:
        print(f"[openWakeWord] Aviso ao preparar modelos: {exc}")
        return False


class OpenWakeWordDetector:
    """
    Detector acústico de Wake Word em streaming usando `openwakeword.Model` (ONNX).
    Mantém um acumulador de amostras PCM16 para alimentar blocos exatos de 1280 amostras (80ms).
    """

    def __init__(
        self,
        threshold: float | None = None,
        vad_threshold: float | None = None,
        use_verifier: bool = True,
    ) -> None:
        self.threshold: float = _limiar_oww() if threshold is None else threshold
        self.vad_threshold: float = _limiar_vad() if vad_threshold is None else vad_threshold
        self.use_verifier: bool = use_verifier
        self.ultimo_score: float = 0.0
        self.pico_recente: float = 0.0
        self._lock = threading.Lock()
        self._pcm_remainder = np.array([], dtype=np.int16)
        self._oww_model: Any = None
        self.disponivel: bool = False
        self._carregar()

    def _carregar(self) -> None:
        if not garantir_modelos_openwakeword():
            self.disponivel = False
            return
        try:
            from openwakeword.model import Model

            verifier_dict: dict[str, str] = {}
            if self.use_verifier and FRYIVS_VERIFIER_PATH.exists():
                verifier_dict = {"fryivs": str(FRYIVS_VERIFIER_PATH)}

            self._oww_model = Model(
                wakeword_models=[str(FRYIVS_ONNX_PATH)],
                custom_verifier_models=verifier_dict,
                custom_verifier_threshold=0.25,
                vad_threshold=self.vad_threshold,
                inference_framework="onnx",
            )
            self.disponivel = True
        except Exception as exc:
            print(f"[openWakeWord] Falha ao inicializar Model ONNX: {exc}")
            self._oww_model = None
            self.disponivel = False

    def reset(self) -> None:
        """Limpa os buffers de predição e features do openWakeWord."""
        with self._lock:
            self._pcm_remainder = np.array([], dtype=np.int16)
            self.ultimo_score = 0.0
            self.pico_recente = 0.0
            if self._oww_model is not None:
                try:
                    self._oww_model.reset()
                except Exception:
                    pass

    def processar_chunk(self, audio_chunk: np.ndarray) -> tuple[bool, float]:
        """
        Alimenta um bloco de áudio (ex.: 1600 amostras = 100ms float32) no motor openWakeWord
        em passos de 1280 amostras (80ms) e retorna `(ativou_wake, max_score_no_bloco)`.
        """
        if not self.disponivel or self._oww_model is None:
            return False, 0.0

        pcm = float32_to_pcm16(audio_chunk)
        if len(pcm) == 0:
            return False, 0.0

        with self._lock:
            if len(self._pcm_remainder) > 0:
                pcm = np.concatenate([self._pcm_remainder, pcm])

            max_score = 0.0
            offset = 0
            while offset + OWW_STEP_SAMPLES <= len(pcm):
                frame = pcm[offset : offset + OWW_STEP_SAMPLES]
                offset += OWW_STEP_SAMPLES
                preds = self._oww_model.predict(frame)
                score = float(preds.get("fryivs", 0.0))
                if score > max_score:
                    max_score = score

            self._pcm_remainder = pcm[offset:]
            self.ultimo_score = max_score
            if max_score > self.pico_recente:
                self.pico_recente = max_score

            return max_score >= self.threshold, max_score

    def detectar_em_segmento(self, audio_segment: np.ndarray) -> tuple[bool, float]:
        """
        Avalia um segmento completo de áudio (ex.: uma elocução inteira) usando o modelo
        openWakeWord isolado (com padding inicial e final) e retorna `(detectou, max_score)`.
        """
        if not self.disponivel or self._oww_model is None:
            return False, 0.0

        pcm_core = float32_to_pcm16(audio_segment)
        if len(pcm_core) == 0:
            return False, 0.0

        pad = np.zeros(8000, dtype=np.int16)
        pcm = np.concatenate([pad, pcm_core, pad])

        with self._lock:
            self._oww_model.reset()
            old_vad = getattr(self._oww_model, "vad_threshold", 0.0)
            self._oww_model.vad_threshold = 0.0
            max_score = 0.0
            try:
                for idx in range(0, len(pcm) - OWW_STEP_SAMPLES + 1, OWW_STEP_SAMPLES):
                    preds = self._oww_model.predict(pcm[idx : idx + OWW_STEP_SAMPLES])
                    score = float(preds.get("fryivs", 0.0))
                    if score > max_score:
                        max_score = score
            finally:
                self._oww_model.vad_threshold = old_vad
                self._oww_model.reset()

            self.ultimo_score = max_score
            return max_score >= self.threshold, max_score

    def status(self) -> dict[str, Any]:
        return {
            "engine": "openWakeWord (ONNX)",
            "available": self.disponivel,
            "model_path": str(FRYIVS_ONNX_PATH),
            "verifier_enabled": bool(self.use_verifier and FRYIVS_VERIFIER_PATH.exists()),
            "threshold": self.threshold,
            "vad_threshold": self.vad_threshold,
            "last_score": round(self.ultimo_score, 4),
            "recent_peak": round(self.pico_recente, 4),
        }


_detector_singleton: OpenWakeWordDetector | None = None
_singleton_lock = threading.Lock()


def obter_detector_openwakeword() -> OpenWakeWordDetector:
    """Retorna a instância singleton do detector `openWakeWord`."""
    global _detector_singleton
    with _singleton_lock:
        if _detector_singleton is None:
            _detector_singleton = OpenWakeWordDetector()
        return _detector_singleton

