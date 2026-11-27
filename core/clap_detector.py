"""
Detector acústico em tempo real de Duas Palmas (Double-Clap Wake Trigger) para F.R.Y.I.Vs.

Inspirado em https://github.com/Aariyan007/Clap_on_Jarvis, evoluído para operar no mesmo
stream mono de 16 kHz do `VoiceDaemon` (sem abrir um segundo `sounddevice.InputStream`) e
com 3 camadas anti-falso-positivo para rejeitar fala humana e batidas graves na mesa:
1. Limiar adaptativo acima do piso de ruído calibrado do ambiente.
2. Fator de crista impulsivo (`peak / rms`) + verificação de decaimento rápido (< 64 ms).
3. Razão espectral de alta frequência (`> 1400 Hz`) característica de palmas percussivas.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

SAMPLE_RATE_DEFAULT = 16000
SUBFRAME_SAMPLES = 256  # 16ms @ 16kHz


@dataclass(frozen=True)
class ClapSensitivityPreset:
    name: str
    min_peak: float
    min_crest: float
    min_hf_ratio: float
    ambient_multiplier: float
    max_hot_subframes: int


SENSITIVITY_PRESETS: dict[str, ClapSensitivityPreset] = {
    "alta": ClapSensitivityPreset(
        name="alta",
        min_peak=0.055,
        min_crest=2.65,
        min_hf_ratio=0.15,
        ambient_multiplier=2.8,
        max_hot_subframes=3,
    ),
    "media": ClapSensitivityPreset(
        name="media",
        min_peak=0.085,
        min_crest=3.10,
        min_hf_ratio=0.19,
        ambient_multiplier=3.3,
        max_hot_subframes=3,
    ),
    "baixa": ClapSensitivityPreset(
        name="baixa",
        min_peak=0.130,
        min_crest=3.55,
        min_hf_ratio=0.24,
        ambient_multiplier=3.9,
        max_hot_subframes=2,
    ),
}


class ClapDetector:
    """
    Detector determinístico de duas palmas consecutivas dentro da janela
    `[min_clap_interval, clap_gap]` com proteção de `cooldown`.
    """

    def __init__(
        self,
        enabled: bool | None = None,
        sensitivity: str | None = None,
        min_clap_interval: float = 0.14,
        clap_gap: float = 0.78,
        cooldown: float = 2.5,
        sample_rate: int = SAMPLE_RATE_DEFAULT,
    ) -> None:
        env_enabled = os.getenv("CLAP_WAKE_ENABLED", "true").strip().lower()
        if enabled is None:
            enabled = env_enabled not in ("false", "0", "no", "nao", "não")
        env_sens = (sensitivity or os.getenv("CLAP_SENSITIVITY", "media")).strip().lower()
        if env_sens not in SENSITIVITY_PRESETS:
            env_sens = "media"

        self._lock = threading.Lock()
        self.enabled: bool = bool(enabled)
        self.sensitivity: str = env_sens
        self.min_clap_interval: float = float(min_clap_interval)
        self.clap_gap: float = float(clap_gap)
        self.cooldown: float = float(cooldown)
        self.sample_rate: int = int(sample_rate)

        self._clap_times: list[float] = []
        self._last_clap_time: float = -10.0
        self._last_trigger_time: float = -10.0
        self.total_triggers: int = 0
        self.last_peak: float = 0.0

    def reset(self) -> None:
        with self._lock:
            self._clap_times.clear()

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self.enabled = bool(enabled)
            self._clap_times.clear()
        return self.status()

    def set_sensitivity(self, sensitivity: str) -> dict[str, Any]:
        norm = (sensitivity or "").strip().lower()
        aliases = {
            "low": "baixa",
            "baixa": "baixa",
            "medium": "media",
            "média": "media",
            "media": "media",
            "padrao": "media",
            "padrão": "media",
            "high": "alta",
            "alta": "alta",
        }
        resolved = aliases.get(norm)
        if not resolved:
            raise ValueError(
                f"Sensibilidade inválida '{sensitivity}'. Use: baixa, media ou alta."
            )
        with self._lock:
            self.sensitivity = resolved
            self._clap_times.clear()
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            preset = SENSITIVITY_PRESETS[self.sensitivity]
            return {
                "enabled": self.enabled,
                "sensitivity": self.sensitivity,
                "min_peak": preset.min_peak,
                "clap_gap_seconds": self.clap_gap,
                "min_interval_seconds": self.min_clap_interval,
                "cooldown_seconds": self.cooldown,
                "total_triggers": self.total_triggers,
                "last_peak": round(self.last_peak, 4),
            }

    @staticmethod
    def _high_freq_ratio(frame: np.ndarray, sample_rate: int, cutoff_hz: float = 1400.0) -> float:
        spec = np.abs(np.fft.rfft(frame * np.hanning(len(frame)))) ** 2
        total_energy = float(np.sum(spec))
        if total_energy <= 1e-12:
            return 0.0
        freqs = np.fft.rfftfreq(len(frame), d=1.0 / float(sample_rate))
        hf_energy = float(np.sum(spec[freqs >= cutoff_hz]))
        return hf_energy / total_energy

    def process_chunk(
        self,
        chunk: np.ndarray,
        ambient_rms: float = 0.045,
        now: float | None = None,
    ) -> tuple[bool, int]:
        """
        Analisa um bloco de áudio (tipicamente 100ms = 1600 amostras @ 16 kHz).

        Retorna `(double_clap_detected, claps_in_window)`.
        """
        flat = np.asarray(chunk, dtype=np.float32).flatten()
        if len(flat) < SUBFRAME_SAMPLES:
            return False, 0

        base_now = time.monotonic() if now is None else float(now)

        with self._lock:
            if not self.enabled:
                return False, 0
            if base_now - self._last_trigger_time < self.cooldown:
                return False, 0

            preset = SENSITIVITY_PRESETS[self.sensitivity]
            dyn_peak_floor = max(preset.min_peak, float(ambient_rms) * preset.ambient_multiplier)

            # Rejeita fala sustentada ou grito: conta quantos sub-blocos de 16ms têm RMS elevado
            n_sub = len(flat) // SUBFRAME_SAMPLES
            subframes = [
                flat[i * SUBFRAME_SAMPLES : (i + 1) * SUBFRAME_SAMPLES] for i in range(n_sub)
            ]
            sub_rms = [float(np.sqrt(np.mean(sf * sf))) for sf in subframes]
            sub_peaks = [float(np.max(np.abs(sf))) for sf in subframes]

            hot_threshold = max(float(ambient_rms) * 2.1, dyn_peak_floor * 0.36)
            hot_count = sum(1 for r in sub_rms if r >= hot_threshold)
            if hot_count > preset.max_hot_subframes:
                return False, len(self._clap_times)

            best_idx = int(np.argmax(sub_peaks))
            peak = sub_peaks[best_idx]
            if peak < dyn_peak_floor:
                # Limpa palmas expiradas da janela
                self._clap_times = [t for t in self._clap_times if base_now - t <= self.clap_gap]
                return False, len(self._clap_times)

            # Calcula fator de crista sobre a vizinhança do pulso e do bloco inteiro
            chunk_rms = float(np.sqrt(np.mean(flat * flat))) + 1e-7
            crest = peak / chunk_rms
            if crest < preset.min_crest:
                return False, len(self._clap_times)

            hf_ratio = self._high_freq_ratio(subframes[best_idx], self.sample_rate)
            if hf_ratio < preset.min_hf_ratio:
                return False, len(self._clap_times)

            clap_ts = base_now + (best_idx * SUBFRAME_SAMPLES) / float(self.sample_rate)
            if clap_ts - self._last_clap_time < self.min_clap_interval:
                return False, len(self._clap_times)

            self._last_clap_time = clap_ts
            self.last_peak = peak
            self._clap_times = [
                t for t in self._clap_times if (clap_ts - t) <= self.clap_gap
            ]
            self._clap_times.append(clap_ts)

            if len(self._clap_times) >= 2:
                gap = self._clap_times[-1] - self._clap_times[-2]
                if self.min_clap_interval <= gap <= self.clap_gap:
                    self._clap_times.clear()
                    self._last_trigger_time = clap_ts
                    self.total_triggers += 1
                    print(
                        f"[ClapDetector] Duas palmas confirmadas! "
                        f"(gap={gap:.2f}s, peak={peak:.3f}, crest={crest:.2f}, hf={hf_ratio:.2f})"
                    )
                    return True, 2

            return False, len(self._clap_times)


_GLOBAL_CLAP_DETECTOR: ClapDetector | None = None
_GLOBAL_CLAP_LOCK = threading.Lock()


def get_clap_detector() -> ClapDetector:
    global _GLOBAL_CLAP_DETECTOR
    with _GLOBAL_CLAP_LOCK:
        if _GLOBAL_CLAP_DETECTOR is None:
            _GLOBAL_CLAP_DETECTOR = ClapDetector()
        return _GLOBAL_CLAP_DETECTOR

