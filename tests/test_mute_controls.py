"""
Testes unitários e de integração para o sistema de Mute de Entrada e Saída de Voz
e Acionamento Exclusivo por Wake Word da F.R.Y.I.Vs.
"""
import numpy as np
import pytest
from starlette.testclient import TestClient

from core import mute_state
from core.voice_daemon import VoiceDaemon
from core.tts import falar
from core.audio_player import tocar
import server


@pytest.fixture(autouse=True)
def reset_mute():
    """Garante que todo teste inicia e termina com mute desativado."""
    mute_state.set_muted(False)
    yield
    mute_state.set_muted(False)


def test_mute_state_toggle():
    assert not mute_state.is_muted()
    mute_state.set_muted(True)
    assert mute_state.is_muted()
    mute_state.set_muted(False)
    assert not mute_state.is_muted()


def test_tts_falar_bloqueado_quando_mutado():
    mute_state.set_muted(True)
    resultado = falar("Olá senhor, este teste não deve gerar voz.")
    assert resultado == ""


def test_audio_player_tocar_bloqueado_quando_mutado(tmp_path):
    arquivo_falso = tmp_path / "audio_teste.mp3"
    arquivo_falso.write_bytes(b"dummy mp3 data")

    mute_state.set_muted(True)
    assert not tocar(str(arquivo_falso), bloquear=False)


def test_voice_daemon_descarta_chunks_quando_mutado():
    notificacoes = []
    daemon = VoiceDaemon(
        notificar_fn=lambda ev: notificacoes.append(ev),
        limiar_inicial=0.01,
        usar_openwakeword=False,
    )

    chunk_fala = np.full(1600, 0.5, dtype=np.float32)

    daemon.set_muted(True)
    assert mute_state.is_muted()
    assert daemon.estado == "DORMINDO"
    assert any(n.get("type") == "mic_muted" and n.get("muted") is True for n in notificacoes)

    for _ in range(10):
        daemon.processar_chunk(chunk_fala)

    assert daemon.estado == "DORMINDO"
    assert len(daemon._chunks_fala) == 0

    daemon.set_muted(False)
    assert not mute_state.is_muted()
    assert any(n.get("type") == "mic_muted" and n.get("muted") is False for n in notificacoes)


def test_api_mute_endpoints():
    client = TestClient(server.app)

    res = client.post("/api/voice/mute", json={"muted": True})
    assert res.status_code == 200
    assert mute_state.is_muted()

    res_get = client.get("/api/voice/mute")
    assert res_get.status_code == 200
    assert res_get.json().get("muted") is True

    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data.get("mic_muted") is True

    res_unmute = client.post("/api/voice/mute", json={"muted": False})
    assert res_unmute.status_code == 200
    assert not mute_state.is_muted()

    res_status_unmute = client.get("/api/status")
    assert res_status_unmute.json().get("mic_muted") is False


def test_api_voice_trigger():
    client = TestClient(server.app)
    res = client.post("/api/voice/trigger")
    assert res.status_code == 200
    assert "triggered" in res.json()

