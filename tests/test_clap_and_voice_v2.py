"""
Testes unitários e de integração para:
1. ClapDetector (duas palmas baseadas em Clap_on_Jarvis + filtros acústicos anti-fala/anti-mesa).
2. Integração VoiceDaemon + ClapDetector (incluindo bloqueio estrito E2EE).
3. Skill configurar_ativacao_palmas + roteamento no SkillRouter.
4. Voz Neural 2.0: humanizar_texto_para_fala, dividir_em_sentencas_fala e falar_streaming_local.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
import numpy as np

from core.clap_detector import ClapDetector, SAMPLE_RATE_DEFAULT
from core.tts import (
    dividir_em_sentencas_fala,
    falar_streaming_local,
    humanizar_texto_para_fala,
    limpar_texto_para_fala,
)
from core.voice_daemon import VoiceDaemon
from skills import SKILLS_REGISTRY, execute_skill


def _make_clap_chunk(peak: float = 0.42, sr: int = SAMPLE_RATE_DEFAULT) -> np.ndarray:
    """Gera um bloco de 100ms contendo um transiente percussivo de palma (1.8–5.5 kHz) de ~12ms."""
    chunk = np.zeros(1600, dtype=np.float32)
    n = 200
    t = np.arange(n, dtype=np.float32) / float(sr)
    envelope = np.exp(-t / 0.0032)
    burst = (
        np.sin(2 * np.pi * 2300.0 * t)
        + 0.8 * np.sin(2 * np.pi * 3700.0 * t + 0.4)
        + 0.6 * np.sin(2 * np.pi * 5100.0 * t + 1.1)
    ) * envelope
    burst = burst / (np.max(np.abs(burst)) + 1e-8) * peak
    chunk[256 : 256 + n] = burst.astype(np.float32)
    return chunk


def _make_desk_thump_chunk(peak: float = 0.45, sr: int = SAMPLE_RATE_DEFAULT) -> np.ndarray:
    """Gera batida grave na mesa (110 Hz) com pico alto mas sem alta frequência."""
    chunk = np.zeros(1600, dtype=np.float32)
    n = 240
    t = np.arange(n, dtype=np.float32) / float(sr)
    burst = np.sin(2 * np.pi * 110.0 * t) * np.exp(-t / 0.008)
    burst = burst / (np.max(np.abs(burst)) + 1e-8) * peak
    chunk[256 : 256 + n] = burst.astype(np.float32)
    return chunk


def _make_speech_chunk(amp: float = 0.28, sr: int = SAMPLE_RATE_DEFAULT) -> np.ndarray:
    """Gera vogal sustentada ao longo dos 100ms (fala contínua)."""
    t = np.arange(1600, dtype=np.float32) / float(sr)
    wave = 0.6 * np.sin(2 * np.pi * 220.0 * t) + 0.4 * np.sin(2 * np.pi * 660.0 * t)
    return (wave / np.max(np.abs(wave)) * amp).astype(np.float32)


def test_clap_detector_confirms_double_clap_and_respects_cooldown() -> None:
    det = ClapDetector(enabled=True, sensitivity="media", min_clap_interval=0.14, clap_gap=0.75, cooldown=2.5)
    clap = _make_clap_chunk()

    ok1, c1 = det.process_chunk(clap, ambient_rms=0.04, now=10.00)
    assert ok1 is False and c1 == 1

    ok2, c2 = det.process_chunk(clap, ambient_rms=0.04, now=10.35)
    assert ok2 is True and c2 == 2
    assert det.total_triggers == 1

    # Durante o cooldown de 2.5s não deve disparar novamente
    ok_cd1, _ = det.process_chunk(clap, ambient_rms=0.04, now=11.00)
    ok_cd2, _ = det.process_chunk(clap, ambient_rms=0.04, now=11.30)
    assert ok_cd1 is False and ok_cd2 is False

    # Após expirar o cooldown, volta a aceitar duas palmas
    det.process_chunk(clap, ambient_rms=0.04, now=13.20)
    ok_after, _ = det.process_chunk(clap, ambient_rms=0.04, now=13.55)
    assert ok_after is True
    assert det.total_triggers == 2


def test_clap_detector_rejects_speech_thumps_and_slow_claps() -> None:
    det = ClapDetector(enabled=True, sensitivity="media")
    speech = _make_speech_chunk()
    thump = _make_desk_thump_chunk()
    clap = _make_clap_chunk()

    # Fala sustentada não conta como palma
    assert det.process_chunk(speech, ambient_rms=0.04, now=1.0)[0] is False
    assert det.process_chunk(speech, ambient_rms=0.04, now=1.3)[0] is False

    # Batida grave na mesa não conta como palma
    assert det.process_chunk(thump, ambient_rms=0.04, now=2.0)[0] is False
    assert det.process_chunk(thump, ambient_rms=0.04, now=2.3)[0] is False

    # Duas palmas muito distantes (> clap_gap) não ativam
    assert det.process_chunk(clap, ambient_rms=0.04, now=5.0) == (False, 1)
    assert det.process_chunk(clap, ambient_rms=0.04, now=6.4) == (False, 1)


def test_voice_daemon_wakes_on_double_clap_and_enforces_e2ee() -> None:
    eventos: list[dict] = []
    senhor_calls: list[int] = []
    stt_calls: list[int] = []

    det = ClapDetector(enabled=True, sensitivity="media", cooldown=0.1)
    daemon = VoiceDaemon(
        transcrever_wake_fn=lambda _a: (stt_calls.append(1) or ""),
        tocar_senhor_fn=lambda: senhor_calls.append(1),
        notificar_fn=eventos.append,
        tocando_fn=lambda: False,
        processando_fn=lambda: False,
        usar_openwakeword=False,
        clap_detector=det,
        usar_clap=True,
    )

    clap = _make_clap_chunk()
    silencio = np.zeros(1600, dtype=np.float32)

    # 1. Quando bloqueada por E2EE, duas palmas NÃO podem acordar a IA
    with patch("core.e2ee_auth.is_session_unlocked", return_value=False):
        daemon.processar_chunk(clap)
        daemon.processar_chunk(silencio)
        daemon.processar_chunk(silencio)
        daemon.processar_chunk(clap)
        assert daemon.estado == "DORMINDO"
        assert len(senhor_calls) == 0

    # 2. Com sessão E2EE desbloqueada, duas palmas acordam imediatamente para OUVINDO_PEDIDO
    det.reset()
    with patch("core.e2ee_auth.is_session_unlocked", return_value=True):
        with patch.object(det, "process_chunk", side_effect=[(False, 1), (False, 1), (False, 1), (True, 2)]):
            daemon.processar_chunk(clap)
            daemon.processar_chunk(silencio)
            daemon.processar_chunk(silencio)
            daemon.processar_chunk(clap)

    assert daemon.estado == "OUVINDO_PEDIDO"
    assert len(senhor_calls) == 1
    assert len(stt_calls) == 0
    assert any(ev.get("type") == "clap_detected" for ev in eventos)


def test_clap_skill_registered_and_controllable() -> None:
    assert "configurar_ativacao_palmas" in SKILLS_REGISTRY
    r1 = execute_skill("configurar_ativacao_palmas", {"acao": "sensibilidade", "sensibilidade": "alta"})
    assert "alta" in r1.lower()

    r2 = execute_skill("configurar_ativacao_palmas", {"acao": "desativar"})
    assert "desativada" in r2.lower()

    r3 = execute_skill("configurar_ativacao_palmas", {"acao": "ativar", "sensibilidade": "media"})
    assert "habilitada" in r3.lower()


def test_humanizar_e_streaming_por_sentencas(tmp_path: Path) -> None:
    bruto = (
        "# Relatório\n"
        "- Servidor em 24°C\n"
        "- Custo US$ 12 com E2EE\n"
        "Veja https://exemplo.com/teste\n"
        "```python\nprint('oi')\n```"
    )
    hum = humanizar_texto_para_fala(bruto)
    assert "24 graus Celsius" in hum
    assert "12 dólares" in hum
    assert "criptografia ponta a ponta" in hum
    assert "https://" not in hum
    assert "print" not in hum
    assert "código detalhado no terminal" in hum
    # Contrato legado intacto
    assert "Frayvis" in limpar_texto_para_fala("Olá F.R.Y.I.Vs!")

    longo = (
        "Olá senhor, concluí toda a varredura de desempenho dos módulos centrais do sistema. "
        "Todos os quatro agentes especialistas estão prontos no escritório tridimensional. "
        "Deseja que eu delegue a próxima pesquisa agora mesmo?"
    )
    partes = dividir_em_sentencas_fala(longo)
    assert len(partes) >= 2

    chamadas_tocar: list[tuple[str, bool]] = []

    def fake_falar(txt: str, output_path=None, unique_file: bool = False) -> str:
        alvo = tmp_path / (f"u_{len(chamadas_tocar)}.mp3" if unique_file else "final.mp3")
        alvo.write_bytes(f"MP3:{txt}".encode("utf-8"))
        return str(alvo)

    out_merged = tmp_path / "resposta_merged.mp3"
    with (
        patch("core.e2ee_auth.is_session_unlocked", return_value=True),
        patch("core.tts.falar", side_effect=fake_falar),
    ):
        caminho_final, tocou = falar_streaming_local(
            longo,
            output_path=str(out_merged),
            tocar_fn=lambda p, b: (chamadas_tocar.append((p, b)) or True),
        )

    assert tocou is True
    assert Path(caminho_final).exists()
    assert len(chamadas_tocar) == len(partes)
    # Primeiras sentenças não bloqueiam; apenas a última bloqueia p/ sincronizar half-duplex
    assert all(b is False for _, b in chamadas_tocar[:-1])
    assert chamadas_tocar[-1][1] is True

