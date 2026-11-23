"""
Suíte completa de testes E2EE & Segurança da F.R.Y.I.Vs.

Valida:
1. Primitivas criptográficas reais: ECDH P-256 (SECP256R1) + HKDF-SHA256 + AES-256-GCM
   + PBKDF2-HMAC-SHA256 (310.000 iterações) + hmac.compare_digest.
2. Handshake E2EE completo (/api/auth/e2ee/status, /unlock, /lock), rejeição de senha errada,
   anti-replay (nonce único, TTL 60s, timestamp stale), detecção de adulteração GCM e rate limit (429).
3. Bloqueio rígido (Hard Lock) quando travado:
   - core/tts.py::falar() recusa gerar áudio
   - core/voice_daemon.py ignora áudio/wake-word e nunca fala "Senhor?" nem executa comandos
   - core/assistant_pipeline.py::processar_comando() recusa LLM/TTS e retorna locked=True
   - server.py bloqueia /api/chat, /api/voice/listen, /api/voice/trigger, /api/voice/daemon (POST),
     /api/audio/*, /api/screen/stream, /api/memory*, /api/skills/execute com HTTP 423 e /ws com 4423.
4. Transporte E2EE opcional em /api/chat (envelope AES-256-GCM ida e volta).
5. Ciclo completo unlock -> uso -> lock, CORS restrito a localhost e ausência de senha hardcoded no frontend.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core import e2ee_auth
from core.stt import CHUNK_SIZE
from core.voice_daemon import VoiceDaemon
import server


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_e2ee_state():
    """Isola completamente o estado E2EE entre testes."""
    e2ee_auth.reset_e2ee_state(lock_enforcement=None)
    yield
    e2ee_auth.reset_e2ee_state(lock_enforcement=None)


@pytest.fixture
def locked_env(monkeypatch):
    """Ativa modo estrito de bloqueio E2EE com senha de teste conhecida."""
    monkeypatch.delenv("FRYIVS_VOICE_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("FRYIVS_VOICE_PASSWORD", "SenhaSuperSecreta#2026!")
    monkeypatch.setenv("FRYIVS_E2EE_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("FRYIVS_E2EE_LOCKOUT_SECONDS", "120")
    e2ee_auth.reset_e2ee_state(lock_enforcement=True)
    return "SenhaSuperSecreta#2026!"


def _do_unlock_handshake(client: TestClient, password: str) -> tuple[str, bytes, dict]:
    """Executa handshake completo ECDH P-256 + HKDF-SHA256 + AES-256-GCM contra a API."""
    st = client.get("/api/auth/e2ee/status")
    assert st.status_code == 200
    status_data = st.json()
    payload, handshake_key, session_key = e2ee_auth.create_encrypted_unlock_payload(
        password=password,
        server_pubkey_jwk=status_data["server_pubkey_jwk"],
        challenge_nonce=status_data["challenge_nonce"],
    )
    res = client.post("/api/auth/e2ee/unlock", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["unlocked"] is True
    assert "session_token" not in body  # Token nunca trafega em texto claro!
    decrypted = e2ee_auth.decrypt_aes_gcm(
        handshake_key,
        body["encrypted_response"]["iv_b64"],
        body["encrypted_response"]["ciphertext_b64"],
        aad=status_data["challenge_nonce"].encode("utf-8"),
    )
    return decrypted["session_token"], session_key, body


# =============================================================================
# 1. Primitivas Criptográficas
# =============================================================================


class TestCryptoPrimitives:
    def test_ecdh_p256_hkdf_aes_256_gcm_roundtrip(self):
        alice_priv, alice_jwk = e2ee_auth.generate_ecdh_keypair()
        bob_priv, bob_jwk = e2ee_auth.generate_ecdh_keypair()

        assert alice_jwk["kty"] == "EC"
        assert alice_jwk["crv"] == "P-256"

        alice_pub_imported = e2ee_auth.jwk_to_public_key(alice_jwk)
        bob_pub_imported = e2ee_auth.jwk_to_public_key(bob_jwk)

        secret_a = e2ee_auth.derive_shared_secret(alice_priv, bob_pub_imported)
        secret_b = e2ee_auth.derive_shared_secret(bob_priv, alice_pub_imported)
        assert len(secret_a) == 32
        assert secret_a == secret_b

        salt = b"nonce-unico-teste-123456"
        key_a = e2ee_auth.derive_aes_key(secret_a, salt=salt)
        key_b = e2ee_auth.derive_aes_key(secret_b, salt=salt)
        assert len(key_a) == 32
        assert key_a == key_b

        msg = {"password": "segredo-neural-ultra", "timestamp": 1700000000}
        env = e2ee_auth.encrypt_aes_gcm(key_a, msg, aad=salt)
        recovered = e2ee_auth.decrypt_aes_gcm(
            key_b, env["iv_b64"], env["ciphertext_b64"], aad=salt
        )
        assert recovered == msg

    def test_aes_gcm_rejeita_ciphertext_ou_aad_adulterado(self):
        key = os.urandom(32)
        aad = b"nonce-original"
        env = e2ee_auth.encrypt_aes_gcm(key, {"secret": "ok"}, aad=aad)

        # AAD diferente deve falhar autenticação GCM
        with pytest.raises(InvalidTag):
            e2ee_auth.decrypt_aes_gcm(key, env["iv_b64"], env["ciphertext_b64"], aad=b"outro-nonce")

        # Flip de 1 bit no ciphertext deve falhar tag GCM
        raw_ct = bytearray(base64.b64decode(env["ciphertext_b64"]))
        raw_ct[0] ^= 0x01
        tampered_b64 = base64.b64encode(bytes(raw_ct)).decode("ascii")
        with pytest.raises(InvalidTag):
            e2ee_auth.decrypt_aes_gcm(key, env["iv_b64"], tampered_b64, aad=aad)

    def test_jwk_invalido_rejeitado(self):
        with pytest.raises(ValueError):
            e2ee_auth.jwk_to_public_key({"kty": "RSA", "crv": "P-256", "x": "AA", "y": "BB"})
        with pytest.raises(ValueError):
            e2ee_auth.jwk_to_public_key({"kty": "EC", "crv": "P-384", "x": "AA", "y": "BB"})
        with pytest.raises(ValueError):
            e2ee_auth.jwk_to_public_key({"kty": "EC", "crv": "P-256", "x": "AAAA", "y": "BBBB"})

    def test_pbkdf2_310k_iterations_e_compare_digest(self):
        assert e2ee_auth.PBKDF2_ITERATIONS == 310_000
        pw_hash = e2ee_auth.hash_password("MinhaSenhaForte@99")
        parts = pw_hash.split("$")
        assert parts[0] == "pbkdf2_sha256"
        assert int(parts[1]) == 310_000

        assert e2ee_auth.verify_password_hash("MinhaSenhaForte@99", pw_hash) is True
        assert e2ee_auth.verify_password_hash("SenhaErrada", pw_hash) is False
        assert e2ee_auth.verify_password_hash("", pw_hash) is False

        # Hash com poucas iterações deve ser rejeitado
        weak_hash = e2ee_auth.hash_password("fraca", iterations=1000)
        assert e2ee_auth.verify_password_hash("fraca", weak_hash) is False

        # Garante uso de hmac.compare_digest (timing-safe)
        src = inspect.getsource(e2ee_auth.verify_password_hash)
        assert "compare_digest" in src

    def test_suporte_a_fryivs_voice_password_hash_via_env(self, monkeypatch):
        pw = "HashDiretoNoEnv#2026"
        pw_hash = e2ee_auth.hash_password(pw)
        monkeypatch.delenv("FRYIVS_VOICE_PASSWORD", raising=False)
        monkeypatch.setenv("FRYIVS_VOICE_PASSWORD_HASH", pw_hash)
        e2ee_auth.reset_e2ee_state(lock_enforcement=True)

        client = TestClient(server.app)
        token, _skey, _body = _do_unlock_handshake(client, pw)
        assert token
        assert e2ee_auth.is_session_unlocked() is True


# =============================================================================
# 2. Handshake, Anti-Replay e Rate Limiting
# =============================================================================


class TestE2EEHandshakeAndSecurityControls:
    def test_status_emite_desafio_efemero_unico(self, locked_env):
        client = TestClient(server.app)
        r1 = client.get("/api/auth/e2ee/status").json()
        r2 = client.get("/api/auth/e2ee/status").json()

        assert r1["required"] is True
        assert r1["unlocked"] is False
        assert r1["has_password_configured"] is True
        assert r1["server_pubkey_jwk"]["crv"] == "P-256"
        assert r1["challenge_nonce"] != r2["challenge_nonce"]
        assert r1["server_pubkey_jwk"]["x"] != r2["server_pubkey_jwk"]["x"]

    def test_senha_errada_rejeitada_e_mantem_bloqueado(self, locked_env):
        client = TestClient(server.app)
        st = client.get("/api/auth/e2ee/status").json()
        payload, _, _ = e2ee_auth.create_encrypted_unlock_payload(
            password="senha-completamente-errada",
            server_pubkey_jwk=st["server_pubkey_jwk"],
            challenge_nonce=st["challenge_nonce"],
        )
        res = client.post("/api/auth/e2ee/unlock", json=payload)
        assert res.status_code == 401
        assert e2ee_auth.is_session_unlocked() is False

    def test_anti_replay_rejeita_reuso_de_nonce(self, locked_env):
        client = TestClient(server.app)
        st = client.get("/api/auth/e2ee/status").json()
        payload, _, _ = e2ee_auth.create_encrypted_unlock_payload(
            password=locked_env,
            server_pubkey_jwk=st["server_pubkey_jwk"],
            challenge_nonce=st["challenge_nonce"],
        )
        # Primeira tentativa válida funciona
        res1 = client.post("/api/auth/e2ee/unlock", json=payload)
        assert res1.status_code == 200

        # Replay exato do mesmo pacote/nonce deve ser rejeitado!
        res2 = client.post("/api/auth/e2ee/unlock", json=payload)
        assert res2.status_code == 401
        assert "anti-replay" in res2.json()["detail"].lower()

    def test_anti_replay_rejeita_nonce_expirado_e_timestamp_antigo(self, locked_env):
        client = TestClient(server.app)

        # 1) Nonce com TTL expirado (> 60s)
        st1 = client.get("/api/auth/e2ee/status").json()
        nonce1 = st1["challenge_nonce"]
        e2ee_auth._challenges[nonce1].created_at = time.time() - (e2ee_auth.CHALLENGE_TTL_SECONDS + 5)
        payload1, _, _ = e2ee_auth.create_encrypted_unlock_payload(
            password=locked_env,
            server_pubkey_jwk=st1["server_pubkey_jwk"],
            challenge_nonce=nonce1,
        )
        res1 = client.post("/api/auth/e2ee/unlock", json=payload1)
        assert res1.status_code == 401

        # 2) Timestamp antigo dentro do payload cifrado (> 60s skew)
        st2 = client.get("/api/auth/e2ee/status").json()
        payload2, _, _ = e2ee_auth.create_encrypted_unlock_payload(
            password=locked_env,
            server_pubkey_jwk=st2["server_pubkey_jwk"],
            challenge_nonce=st2["challenge_nonce"],
            timestamp=time.time() - 300,
        )
        res2 = client.post("/api/auth/e2ee/unlock", json=payload2)
        assert res2.status_code == 401
        assert e2ee_auth.is_session_unlocked() is False

    def test_rate_limit_bloqueia_apos_5_tentativas_falhas(self, locked_env):
        client = TestClient(server.app)

        for attempt in range(4):
            st = client.get("/api/auth/e2ee/status").json()
            payload, _, _ = e2ee_auth.create_encrypted_unlock_payload(
                password=f"errada-{attempt}",
                server_pubkey_jwk=st["server_pubkey_jwk"],
                challenge_nonce=st["challenge_nonce"],
            )
            res = client.post("/api/auth/e2ee/unlock", json=payload)
            assert res.status_code == 401

        # 5ª tentativa falha ativa lockout temporário (HTTP 429)
        st5 = client.get("/api/auth/e2ee/status").json()
        payload5, _, _ = e2ee_auth.create_encrypted_unlock_payload(
            password="errada-5",
            server_pubkey_jwk=st5["server_pubkey_jwk"],
            challenge_nonce=st5["challenge_nonce"],
        )
        res5 = client.post("/api/auth/e2ee/unlock", json=payload5)
        assert res5.status_code == 429
        assert "Retry-After" in res5.headers

        # Mesmo com a senha CORRETA durante lockout, deve continuar bloqueado com 429!
        st6 = client.get("/api/auth/e2ee/status").json()
        assert st6["lockout_remaining_seconds"] > 0
        payload6, _, _ = e2ee_auth.create_encrypted_unlock_payload(
            password=locked_env,
            server_pubkey_jwk=st6["server_pubkey_jwk"],
            challenge_nonce=st6["challenge_nonce"],
        )
        res6 = client.post("/api/auth/e2ee/unlock", json=payload6)
        assert res6.status_code == 429
        assert e2ee_auth.is_session_unlocked() is False


# =============================================================================
# 3. Bloqueio Rígido de Fala, Wake-Word, Pipeline e API/WebSocket
# =============================================================================


class TestHardSpeechAndInteractionLock:
    def test_tts_falar_recusa_gerar_audio_enquanto_bloqueada(self, locked_env, tmp_path):
        from core import tts

        out = str(tmp_path / "bloqueado.mp3")
        with (
            patch.object(tts, "_falar_openai", return_value=out) as mock_oai,
            patch.object(tts, "_falar_edge_tts", return_value=out) as mock_edge,
        ):
            result = tts.falar("Olá senhor, tentando falar bloqueada!", output_path=out)
            assert result == ""
            mock_oai.assert_not_called()
            mock_edge.assert_not_called()

    def test_voice_daemon_ignora_audio_e_nunca_fala_senhor_quando_bloqueado(self, locked_env):
        senhor_tocado = []
        comandos_executados = []
        transcricoes = []

        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: transcricoes.append("wake") or "Frives",
            transcrever_cmd_fn=lambda _a: transcricoes.append("cmd") or "abra o navegador",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda cmd: comandos_executados.append(cmd),
            tocando_fn=lambda: False,
        )

        assert daemon.escuta_habilitada() is False
        assert daemon.acionar_manual() is False

        fala = np.full(CHUNK_SIZE, 0.25, dtype="float32")
        silencio = np.zeros(CHUNK_SIZE, dtype="float32")
        for _ in range(6):
            daemon.processar_chunk(fala)
        for _ in range(6):
            daemon.processar_chunk(silencio)

        # Mesmo chamadas internas diretas devem recusar falar ou executar enquanto bloqueado
        daemon._entrar_modo_senhor()
        daemon._executar_pedido("comando indevido")

        assert transcricoes == []
        assert senhor_tocado == []
        assert comandos_executados == []
        assert daemon.estado == "DORMINDO"

        from core.voice_daemon import garantir_audio_senhor
        assert garantir_audio_senhor() == ""

    def test_assistant_pipeline_recusa_processamento_e_tts_quando_bloqueado(self, locked_env):
        from core.assistant_pipeline import processar_comando

        mock_ask = MagicMock(return_value=("Não deveria responder", []))
        mock_falar = MagicMock(return_value="resposta.mp3")
        mock_salvar = MagicMock()

        result = asyncio.run(
            processar_comando(
                texto="Olá F.R.Y.I.Vs, fale comigo",
                origem="chat",
                generate_speech=True,
                ask_fryvis_fn=mock_ask,
                falar_fn=mock_falar,
                salvar_memoria_fn=mock_salvar,
            )
        )

        assert result["locked"] is True
        assert result["has_audio"] is False
        assert result["played_locally"] is False
        assert "bloqueada" in result["response"].lower()
        mock_ask.assert_not_called()
        mock_falar.assert_not_called()
        mock_salvar.assert_not_called()

    def test_server_bloqueia_todos_endpoints_criticos_com_423_e_ws_4423(self, locked_env):
        client = TestClient(server.app)

        # Endpoints HTTP protegidos devem retornar 423 Locked
        assert client.post("/api/chat", json={"message": "oi"}).status_code == 423
        assert client.post("/api/voice/listen").status_code == 423
        assert client.post("/api/voice/trigger").status_code == 423
        assert client.post("/api/voice/daemon", json={"enabled": True}).status_code == 423
        assert client.get("/api/audio/last").status_code == 423
        assert client.get("/api/audio/req123").status_code == 423
        assert client.get("/api/screen/stream").status_code == 423
        assert client.get("/api/memory").status_code == 423
        assert client.delete("/api/memory/mem-1").status_code == 423
        assert client.post("/api/skills/execute", json={"skill": "listar_janelas", "arguments": {}}).status_code == 423

        # WebSocket deve ser fechado com código 4423
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
        assert exc_info.value.code == 4423

        # /api/status e /api/auth/e2ee/status permanecem acessíveis para exibir tela de bloqueio
        st = client.get("/api/status")
        assert st.status_code == 200
        assert st.json()["e2ee_required"] is True
        assert st.json()["e2ee_unlocked"] is False


# =============================================================================
# 4. Ciclo Completo Unlock -> Chat E2EE & Voz -> Lock
# =============================================================================


class TestFullE2EELifecycleAndEncryptedChat:
    @patch("server.buscar_contexto", return_value="")
    @patch("server.ask_fryvis", return_value=("Acesso liberado, senhor!", []))
    @patch("server.salvar_memoria")
    @patch("server.falar", return_value="")
    def test_unlock_chat_e2ee_envelope_ws_e_lock(
        self, mock_falar, mock_salvar, mock_ask, mock_buscar, locked_env
    ):
        client = TestClient(server.app)

        # 1. Bloqueado inicialmente
        assert client.post("/api/chat", json={"message": "oi"}).status_code == 423

        # 2. Handshake E2EE desbloqueia sessão
        session_token, session_key, _ = _do_unlock_handshake(client, locked_env)
        assert e2ee_auth.is_session_unlocked() is True

        # 3. Outro cliente SEM token continua recebendo 423!
        assert client.post("/api/chat", json={"message": "invasor"}).status_code == 423
        assert client.get("/api/memory").status_code == 423

        # 4. Cliente COM token mas texto plano funciona
        res_plain = client.post(
            "/api/chat",
            headers={"X-E2EE-Session": session_token},
            json={"message": "Olá FRYIVS", "generate_speech": False, "use_memory": False},
        )
        assert res_plain.status_code == 200
        assert res_plain.json()["response"] == "Acesso liberado, senhor!"

        # 5. Cliente COM transporte E2EE criptografado no /api/chat (envelope AES-256-GCM)
        envelope_in = e2ee_auth.encrypt_aes_gcm(
            session_key,
            {
                "message": "Mensagem confidencial E2EE",
                "generate_speech": False,
                "use_memory": False,
            },
            aad=e2ee_auth.CHAT_AAD,
        )
        res_enc = client.post(
            "/api/chat",
            headers={"X-E2EE-Session": session_token},
            json={"e2ee": envelope_in},
        )
        assert res_enc.status_code == 200
        enc_body = res_enc.json()
        assert enc_body["encrypted"] is True
        assert "response" not in enc_body  # Sem vazamento em texto claro!
        decrypted_resp = e2ee_auth.decrypt_aes_gcm(
            session_key,
            enc_body["e2ee"]["iv_b64"],
            enc_body["e2ee"]["ciphertext_b64"],
            aad=e2ee_auth.CHAT_AAD,
        )
        assert decrypted_resp["user_message"] == "Mensagem confidencial E2EE"
        assert decrypted_resp["response"] == "Acesso liberado, senhor!"

        # 5b. Envelope E2EE adulterado no /api/chat deve ser rejeitado (400)
        raw_ct = bytearray(base64.b64decode(envelope_in["ciphertext_b64"]))
        raw_ct[0] ^= 0xFF
        tampered_env = {
            "iv_b64": envelope_in["iv_b64"],
            "ciphertext_b64": base64.b64encode(bytes(raw_ct)).decode("ascii"),
        }
        res_tampered = client.post(
            "/api/chat",
            headers={"X-E2EE-Session": session_token},
            json={"e2ee": tampered_env},
        )
        assert res_tampered.status_code == 400

        # 6. WebSocket autenticado com e2ee_token funciona
        with client.websocket_connect(f"/ws?e2ee_token={session_token}") as ws:
            welcome = ws.receive_json()
            assert welcome["type"] == "welcome"
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"

        # 7. VoiceDaemon volta a permitir escuta quando desbloqueado
        senhor_tocado = []
        daemon = VoiceDaemon(
            transcrever_wake_fn=lambda _a: "Frives",
            tocar_senhor_fn=lambda: senhor_tocado.append(True),
            executar_comando_fn=lambda _c: None,
            tocando_fn=lambda: False,
        )
        assert daemon.escuta_habilitada() is True

        # 8. Bloqueia imediatamente via POST /api/auth/e2ee/lock
        lock_res = client.post("/api/auth/e2ee/lock", headers={"X-E2EE-Session": session_token})
        assert lock_res.status_code == 200
        assert lock_res.json()["unlocked"] is False
        assert e2ee_auth.is_session_unlocked() is False

        # 9. Token antigo imediatamente revogado -> 423 / WS 4423 / Daemon travado
        assert (
            client.post(
                "/api/chat",
                headers={"X-E2EE-Session": session_token},
                json={"message": "ainda funciona?"},
            ).status_code
            == 423
        )
        assert daemon.escuta_habilitada() is False
        with pytest.raises(WebSocketDisconnect) as exc_after:
            with client.websocket_connect(f"/ws?e2ee_token={session_token}") as ws:
                ws.receive_json()
        assert exc_after.value.code == 4423


# =============================================================================
# 5. Higiene de Segurança: CORS e Ausência de Senha Hardcoded no Frontend
# =============================================================================


class TestSecurityHygiene:
    def test_cors_restrito_a_localhost(self):
        client = TestClient(server.app)

        # Origem local permitida
        res_ok = client.options(
            "/api/status",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res_ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"

        # Origem externa maliciosa NÃO pode receber Allow-Origin
        res_evil = client.options(
            "/api/status",
            headers={
                "Origin": "https://evil-attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res_evil.headers.get("access-control-allow-origin") is None

    def test_sem_senha_hardcoded_no_frontend(self):
        app_tsx = (ROOT / "ui" / "react-app" / "src" / "App.tsx").read_text(encoding="utf-8")
        assert "fryivslendaria" not in app_tsx.lower()

        bundle = ROOT / "ui" / "static" / "react" / "fryvis-react.js"
        if bundle.exists():
            bundle_txt = bundle.read_text(encoding="utf-8", errors="ignore")
            assert "fryivslendaria" not in bundle_txt.lower()

    def test_runtime_padrao_exige_e2ee_e_bypass_apenas_em_pytest(self, monkeypatch):
        # Fora de PYTEST_CURRENT_TEST e sem env definida -> default DEVE ser True (fail-closed)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("FRYIVS_REQUIRE_E2EE_PASSWORD", raising=False)
        e2ee_auth.reset_e2ee_state(lock_enforcement=None)
        assert e2ee_auth.is_e2ee_required() is True
        assert e2ee_auth.is_session_unlocked() is False

        # Explicitamente false desativa
        monkeypatch.setenv("FRYIVS_REQUIRE_E2EE_PASSWORD", "false")
        assert e2ee_auth.is_e2ee_required() is False
        assert e2ee_auth.is_session_unlocked() is True

    def test_sem_env_de_senha_gera_hash_efemero_sem_estatico(self, monkeypatch):
        monkeypatch.delenv("FRYIVS_VOICE_PASSWORD", raising=False)
        monkeypatch.delenv("FRYIVS_VOICE_PASSWORD_HASH", raising=False)
        e2ee_auth.reset_e2ee_state(lock_enforcement=True)
        h1, configured = e2ee_auth._get_active_password_hash()
        assert configured is False
        assert h1.startswith("pbkdf2_sha256$310000$")
        assert e2ee_auth.verify_password_hash("fryivslendaria", h1) is False
        assert e2ee_auth.verify_password_hash("admin", h1) is False
        assert e2ee_auth.verify_password_hash("123456", h1) is False
