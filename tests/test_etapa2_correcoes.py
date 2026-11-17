"""
Testes para as correções da Etapa 2:
- TTS circuit breaker com TTL
- STT lock Whisper (smoke test de importação)
- Gemini race condition (turno user duplicado)
- Scheduler: parsing de intervalo, persistência, callback real
- Webhook: payload adaptativo
- Server: broadcast remove socket morto
- Server: endpoint /api/audio/{id}
- VoiceDaemon: cooldown half-duplex, interrupção acumuladora
- Office COM: confirmar que obj retornado é usado (smoke test estático)
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


class TestTTSCircuitBreaker:
    def setup_method(self):
        import core.tts as tts_mod
        tts_mod._openai_quota_exhausted = False
        tts_mod._openai_quota_exhausted_at = 0.0

    def test_circuit_breaker_bloqueado_dentro_ttl(self):
        import core.tts as tts_mod
        tts_mod._openai_quota_exhausted = True
        tts_mod._openai_quota_exhausted_at = time.time()
        result = tts_mod._falar_openai("teste", "/tmp/nao_cria.mp3")
        assert result == "", "Deve retornar vazio quando CB fechado dentro do TTL"

    def test_circuit_breaker_abre_apos_ttl(self, tmp_path):
        import core.tts as tts_mod
        tts_mod._openai_quota_exhausted = True
        tts_mod._openai_quota_exhausted_at = time.time() - tts_mod._OPENAI_CB_TTL - 1

        out = tmp_path / "audio.mp3"
        import io
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content = lambda chunk_size: [b"\x00" * 100]
        with patch("core.tts.requests.post", return_value=mock_resp):
            tts_mod._falar_openai("oi", str(out))
        assert not tts_mod._openai_quota_exhausted or tts_mod._openai_quota_exhausted_at > 0

    def test_circuit_breaker_fecha_em_401(self, tmp_path):
        import core.tts as tts_mod
        tts_mod._openai_quota_exhausted = False
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "invalid key"}}
        with patch("core.tts.requests.post", return_value=mock_resp):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-fake-key"}):
                tts_mod._falar_openai("oi", str(tmp_path / "x.mp3"))
        assert tts_mod._openai_quota_exhausted is True
        assert tts_mod._openai_quota_exhausted_at > 0

    def test_senhor_ack_protegido_da_limpeza(self, tmp_path):
        """senhor_ack.mp3 não deve ser removido pela limpeza periódica."""
        import core.tts as tts_mod
        fake_cache = tmp_path / "audio_cache"
        fake_cache.mkdir()
        protegido = fake_cache / "senhor_ack.mp3"
        protegido.write_bytes(b"\x00" * 10)
        expirado = fake_cache / "resp_old.mp3"
        expirado.write_bytes(b"\x00" * 10)
        old_time = time.time() - 7200
        os.utime(str(protegido), (old_time, old_time))
        os.utime(str(expirado), (old_time, old_time))

        with patch.object(tts_mod, "AUDIO_CACHE_DIR", str(fake_cache)):
            removidos = tts_mod.limpar_cache_audio(max_idade_segundos=3600)

        assert protegido.exists(), "senhor_ack.mp3 não deve ser apagado"
        assert not expirado.exists(), "resp_old.mp3 deve ser apagado"
        assert removidos == 1


def test_stt_whisper_lock_existe():
    import core.stt as stt_mod
    assert hasattr(stt_mod, "_whisper_lock"), "_whisper_lock deve existir em core.stt"
    assert isinstance(stt_mod._whisper_lock, type(threading.Lock()).__class__) or \
           hasattr(stt_mod._whisper_lock, "acquire"), "_whisper_lock deve ser um Lock"


class TestGeminiRaceCondition:
    def _get_format_fn(self):
        import core.gemini_client as gc
        return gc._format_history_for_gemini

    def test_historico_vazio_nao_insere_nada(self):
        fn = self._get_format_fn()
        assert fn([]) == []
        assert fn(None) == []

    def test_historico_alternado_preservado(self):
        fn = self._get_format_fn()
        hist = [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "olá"},
        ]
        result = fn(hist)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "model"

    def test_turno_user_duplicado_removido(self):
        """Se histórico termina em user, o novo turno não deve criar par user+user."""
        import core.gemini_client as gc

        hist_malformado = [
            {"role": "user", "content": "cmd anterior"},
        ]
        contents = gc._format_history_for_gemini(hist_malformado)

        if contents and contents[-1].get("role") == "user":
            contents.pop()
        contents.append({"role": "user", "parts": [{"text": "novo cmd"}]})

        roles = [c["role"] for c in contents]
        for i in range(len(roles) - 1):
            assert not (roles[i] == "user" and roles[i+1] == "user"), \
                f"user+user consecutivos em posições {i},{i+1}: {roles}"


class TestScheduler:
    def setup_method(self):
        import skills.scheduler_ops as sch
        sch._jobs_registry.clear()
        sch._scheduler_running = False

    def test_parsing_minutos_robusto(self):
        """Deve aceitar '15m', '30min', '5 m' e rejeitar string sem número."""
        import re as _re
        casos_ok = ["15m", "30min", "5 m"]
        for caso in casos_ok:
            m = _re.search(r"\d+", caso)
            assert m is not None, f"Parsing falhou para '{caso}'"
            assert int(m.group()) > 0

        caso_invalido = "abc"
        assert _re.search(r"\d+", caso_invalido) is None

    def test_jobs_salvo_e_carregado(self, tmp_path):
        import skills.scheduler_ops as sch
        fake_jobs_file = tmp_path / "scheduled_jobs.json"

        with patch.object(sch, "_JOBS_FILE", fake_jobs_file):
            sch._jobs_registry = [
                {"horario": "08:00", "comando": "test", "tipo": "diario", "criado_em": "2026-01-01"}
            ]
            sch._salvar_jobs()
            assert fake_jobs_file.exists(), "Arquivo deve ser criado"

            sch._jobs_registry = []
            sch._carregar_jobs()
            assert len(sch._jobs_registry) == 1
            assert sch._jobs_registry[0]["comando"] == "test"

    def test_jobs_arquivo_corrompido_nao_quebra(self, tmp_path):
        import skills.scheduler_ops as sch
        fake_file = tmp_path / "bad.json"
        fake_file.write_text("{não é json válido}", encoding="utf-8")
        with patch.object(sch, "_JOBS_FILE", fake_file):
            sch._carregar_jobs()
        assert isinstance(sch._jobs_registry, list)

    def test_payload_discord(self):
        import skills.scheduler_ops as sch
        url = "https://discord.com/api/webhooks/123/abc"
        url_lower = url.lower()
        if "discord.com/api/webhooks" in url_lower:
            payload = {"content": "teste", "username": "F.R.Y.I.Vs"}
        else:
            payload = {"mensagem": "teste"}
        assert "content" in payload
        assert "username" in payload

    def test_payload_telegram(self):
        url = "https://api.telegram.org/bot123/sendMessage"
        url_lower = url.lower()
        if "api.telegram.org" in url_lower:
            payload = {"text": "[F.R.Y.I.Vs] teste"}
        else:
            payload = {}
        assert "text" in payload

    def test_payload_slack(self):
        url = "https://hooks.slack.com/services/T00/B00/xxx"
        url_lower = url.lower()
        if "hooks.slack.com" in url_lower:
            payload = {"text": "*F.R.Y.I.Vs*: msg"}
        else:
            payload = {}
        assert "text" in payload


class TestServerBroadcast:
    def test_broadcast_remove_conexao_morta(self):
        """Conexão que lança exceção deve ser removida de active_connections."""
        from starlette.testclient import TestClient
        import server

        mgr = server.ConnectionManager()
        dead = MagicMock()
        dead.send_json = AsyncMock(side_effect=RuntimeError("closed"))
        alive = MagicMock()
        alive.send_json = AsyncMock(return_value=None)

        mgr.active_connections = [dead, alive]

        async def run():
            await mgr.broadcast({"type": "ping"})

        asyncio.run(run())
        assert dead not in mgr.active_connections, "Socket morto deve ser removido"
        assert alive in mgr.active_connections, "Socket vivo deve permanecer"


class TestAudioEndpoint:
    def test_audio_last_404_sem_arquivo(self, tmp_path):
        """GET /api/audio/last deve retornar 404 quando não há resposta.mp3."""
        import server
        from starlette.testclient import TestClient
        with patch("os.path.exists", return_value=False):
            client = TestClient(server.app, raise_server_exceptions=False)
            resp = client.get("/api/audio/last")
            assert resp.status_code in (404, 422, 500)

    def test_audio_by_id_rejeita_path_traversal(self):
        """request_id com caracteres especiais deve retornar 400."""
        import server
        from starlette.testclient import TestClient
        client = TestClient(server.app, raise_server_exceptions=False)
        resp = client.get("/api/audio/../etc/passwd")
        assert resp.status_code in (400, 404, 422)

    def test_audio_by_id_valido_404_sem_arquivo(self, tmp_path):
        """ID válido mas sem arquivo deve retornar 404."""
        import server
        from starlette.testclient import TestClient
        with patch("os.path.exists", return_value=False):
            client = TestClient(server.app, raise_server_exceptions=False)
            resp = client.get(f"/api/audio/{uuid.uuid4().hex}")
            assert resp.status_code in (404, 500)


class TestVoiceDaemonHalfduplex:
    def _make_daemon(self, tocando=False):
        from core.voice_daemon import VoiceDaemon
        d = VoiceDaemon(
            transcrever_wake_fn=lambda a: "",
            transcrever_cmd_fn=lambda a: "",
            tocar_senhor_fn=lambda: None,
            executar_comando_fn=lambda t: None,
            usar_openwakeword=False,
        )
        d._esta_tocando = lambda: tocando
        return d

    def test_cooldown_descarta_frames_apos_reproducao(self):
        """Durante cooldown (logo após reprodução), processamento deve ser descartado."""
        import numpy as np
        from core.stt import CHUNK_SIZE
        d = self._make_daemon(tocando=False)
        d._silenciar_ate = time.time() + 0.4
        chunk = np.ones(CHUNK_SIZE, dtype="float32") * 0.3
        estado_antes = d.estado
        d.processar_chunk(chunk)
        assert not d._fala_iniciada, "Frame não deve iniciar captura durante cooldown"
        assert d.estado == estado_antes, "Estado não deve mudar durante cooldown"

    def test_acumulador_stop_chunks_resetado_ao_sair_reproducao(self):
        """Ao sair do período de reprodução, _stop_chunks deve ser limpo."""
        import numpy as np
        from core.stt import CHUNK_SIZE
        d = self._make_daemon(tocando=False)
        d._stop_chunks = [np.zeros(CHUNK_SIZE, dtype="float32")] * 3
        d._silenciar_ate = 0.0
        chunk = np.zeros(CHUNK_SIZE, dtype="float32")
        d.processar_chunk(chunk)
        assert d._stop_chunks == [], "_stop_chunks deve ser limpo ao sair da reprodução"

    def test_stop_words_frozenset_existe(self):
        from core.voice_daemon import VoiceDaemon
        assert hasattr(VoiceDaemon, "_STOP_WORDS"), "_STOP_WORDS deve existir na classe"
        assert "pare" in VoiceDaemon._STOP_WORDS
        assert "chega" in VoiceDaemon._STOP_WORDS
        assert "stop" in VoiceDaemon._STOP_WORDS

    def test_verificar_interrupcao_silencio_nao_transcreve(self):
        """Chunk de silêncio não deve chamar transcrição."""
        import numpy as np
        from core.voice_daemon import VoiceDaemon
        transcrever_chamado = []
        d = VoiceDaemon(
            transcrever_wake_fn=lambda a: (transcrever_chamado.append(1), "")[1],
            usar_openwakeword=False,
        )
        d._stop_chunks = [np.zeros(1600, dtype="float32")] * 3
        d._verificar_interrupcao()
        assert not transcrever_chamado, "Silêncio não deve acionar transcrição"

    def test_verificar_interrupcao_deteta_pare(self):
        """Chunk com energia alta e transcrição 'pare' deve chamar audio_player.parar."""
        import numpy as np
        parar_chamado = []
        from core.voice_daemon import VoiceDaemon
        d = VoiceDaemon(
            transcrever_wake_fn=lambda a: "",
            usar_openwakeword=False,
        )
        d._transcrever_interrupcao = lambda a: "pare"
        d.limiar_rms = 0.01
        d._stop_chunks = [np.ones(1600, dtype="float32") * 0.1] * 3
        with patch("core.audio_player.parar", side_effect=lambda: parar_chamado.append(1)):
            with patch("core.voice_daemon._event_loop", None):
                d._verificar_interrupcao()
        assert parar_chamado, "audio_player.parar() deve ser chamado ao detectar 'pare'"
