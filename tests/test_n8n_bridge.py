"""
Suíte completa de testes para a Camada 4 (n8n Bridge, HMAC-SHA256, SSRF Guard,
Skills n8n, Agendador Persistente sem bug Zumbi e Docker Compose Stack).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import schedule
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import e2ee_auth
from core.n8n_bridge import (
    HMAC_HEADER_CORRELATION_ID,
    HMAC_HEADER_NONCE,
    HMAC_HEADER_SIGNATURE,
    HMAC_HEADER_TIMESTAMP,
    N8nBridge,
    get_n8n_bridge,
    n8n_router,
    reset_n8n_bridge,
    sign_webhook_payload,
    validar_url_externa,
    verify_webhook_signature,
)
from skills import n8n_ops, scheduler_ops


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _reset_n8n_and_e2ee():
    reset_n8n_bridge()
    e2ee_auth.reset_e2ee_state(lock_enforcement=None)
    yield
    reset_n8n_bridge()
    e2ee_auth.reset_e2ee_state(lock_enforcement=None)


# =============================================================================
# 1. Assinatura e Verificação HMAC-SHA256 + Anti-Replay (±60s & Nonce)
# =============================================================================


class TestHmacSigningAndVerification:
    def test_sign_and_verify_roundtrip(self):
        secret = "segredo-corporativo-fryivs-2026"
        raw_body = json.dumps({"action": "briefing", "topic": "IA"}, separators=(",", ":"))
        now = 1_750_000_000

        headers = sign_webhook_payload(
            raw_body,
            secret,
            timestamp=now,
            nonce="nonce-unico-abc123",
            correlation_id="corr-001",
        )
        assert headers[HMAC_HEADER_TIMESTAMP] == str(now)
        assert headers[HMAC_HEADER_NONCE] == "nonce-unico-abc123"
        assert headers[HMAC_HEADER_CORRELATION_ID] == "corr-001"
        assert headers[HMAC_HEADER_SIGNATURE].startswith("sha256=")
        assert len(headers[HMAC_HEADER_SIGNATURE]) == len("sha256=") + 64

        ok, reason = verify_webhook_signature(
            raw_body,
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            secret,
            nonce=headers[HMAC_HEADER_NONCE],
            now=now + 10,
            nonce_cache={},
        )
        assert ok is True, reason

    def test_tampered_payload_rejected(self):
        secret = "segredo-corporativo-fryivs-2026"
        now = 1_750_000_000
        headers = sign_webhook_payload('{"action":"status"}', secret, timestamp=now)

        ok, reason = verify_webhook_signature(
            '{"action":"delete_all"}',
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            secret,
            now=now,
        )
        assert ok is False
        assert "inválida" in reason.lower()

    def test_wrong_secret_rejected(self):
        now = 1_750_000_000
        headers = sign_webhook_payload('{"action":"alert"}', "secret-A", timestamp=now)
        ok, _ = verify_webhook_signature(
            '{"action":"alert"}',
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            "secret-B",
            now=now,
        )
        assert ok is False

    def test_replay_window_rejects_stale_and_future_timestamps(self):
        secret = "segredo-replay"
        body = '{"action":"status"}'
        now = 1_750_000_000

        # 61 segundos no passado -> rejeitado
        past_headers = sign_webhook_payload(body, secret, timestamp=now - 61)
        ok_past, reason_past = verify_webhook_signature(
            body,
            past_headers[HMAC_HEADER_TIMESTAMP],
            past_headers[HMAC_HEADER_SIGNATURE],
            secret,
            max_skew_seconds=60,
            now=now,
        )
        assert ok_past is False
        assert "janela" in reason_past.lower() or "anti-replay" in reason_past.lower()

        # 65 segundos no futuro -> rejeitado
        future_headers = sign_webhook_payload(body, secret, timestamp=now + 65)
        ok_future, _ = verify_webhook_signature(
            body,
            future_headers[HMAC_HEADER_TIMESTAMP],
            future_headers[HMAC_HEADER_SIGNATURE],
            secret,
            max_skew_seconds=60,
            now=now,
        )
        assert ok_future is False

        # Exatamente 60s -> aceito
        edge_headers = sign_webhook_payload(body, secret, timestamp=now - 60)
        ok_edge, _ = verify_webhook_signature(
            body,
            edge_headers[HMAC_HEADER_TIMESTAMP],
            edge_headers[HMAC_HEADER_SIGNATURE],
            secret,
            max_skew_seconds=60,
            now=now,
        )
        assert ok_edge is True

    def test_nonce_replay_rejected(self):
        secret = "segredo-nonce"
        body = '{"action":"alert"}'
        now = 1_750_000_000
        headers = sign_webhook_payload(body, secret, timestamp=now, nonce="dup-nonce-1")
        cache: dict[str, float] = {}

        ok1, _ = verify_webhook_signature(
            body,
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            secret,
            nonce="dup-nonce-1",
            now=now,
            nonce_cache=cache,
        )
        ok2, reason2 = verify_webhook_signature(
            body,
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            secret,
            nonce="dup-nonce-1",
            now=now + 1,
            nonce_cache=cache,
        )
        # Replay com X-Fryivs-Nonce removido (stripped) -> também deve ser bloqueado
        ok3, reason3 = verify_webhook_signature(
            body,
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            secret,
            nonce=None,
            now=now + 2,
            nonce_cache=cache,
        )
        # Replay com X-Fryivs-Nonce randomizado/mutado -> também deve ser bloqueado
        ok4, reason4 = verify_webhook_signature(
            body,
            headers[HMAC_HEADER_TIMESTAMP],
            headers[HMAC_HEADER_SIGNATURE],
            secret,
            nonce="brand-new-attacker-nonce",
            now=now + 3,
            nonce_cache=cache,
        )
        assert ok1 is True
        assert ok2 is False
        assert "replay" in reason2.lower() or "nonce" in reason2.lower()
        assert ok3 is False
        assert "replay" in reason3.lower()
        assert ok4 is False
        assert "replay" in reason4.lower()

    def test_missing_secret_or_bad_prefix_rejected(self):
        ok_no_secret, _ = verify_webhook_signature("{}", "1750000000", "sha256=" + "a" * 64, "", now=1750000000)
        assert ok_no_secret is False

        ok_bad_prefix, _ = verify_webhook_signature("{}", "1750000000", "md5=" + "a" * 64, "sec", now=1750000000)
        assert ok_bad_prefix is False


# =============================================================================
# 2. SSRF Guard (`validar_url_externa`)
# =============================================================================


class TestSsrfGuard:
    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "https://169.254.169.254/latest/meta-data/iam/security-credentials/",
            "http://169.254.170.2/v2/credentials",
            "https://metadata.google.internal/computeMetadata/v1/",
            "http://10.0.0.1/admin",
            "https://10.0.0.1/internal",
            "https://172.16.0.5/api",
            "https://192.168.1.1/router",
            "https://100.64.0.1/cgnat",
            "http://127.0.0.1:8000/api/chat",
            "https://127.0.0.1/secret",
            "https://localhost/secret",
            "https://[::1]/secret",
            "https://[::ffff:127.0.0.1]/secret",
            "https://2130706433/obfuscated-loopback",
            "https://0x7f000001/hex-loopback",
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "gopher://127.0.0.1:6379/_INFO",
            "ftp://example.com/file",
            "http://hooks.slack.com/services/insecure-http",
            "https://user:pass@example.com/hook",
            "",
        ],
    )
    def test_blocks_ssrf_and_unsafe_urls(self, bad_url, monkeypatch):
        monkeypatch.delenv("N8N_BASE_URL", raising=False)
        monkeypatch.delenv("N8N_ALLOWED_HOSTS", raising=False)
        ok, reason = validar_url_externa(bad_url)
        assert ok is False, f"URL perigosa deveria ter sido bloqueada: {bad_url!r} (retornou ok={ok}, {reason})"

    def test_allows_public_https_hosts(self, monkeypatch):
        monkeypatch.delenv("N8N_BASE_URL", raising=False)
        ok_slack, _ = validar_url_externa("https://hooks.slack.com/services/T00/B00/XXX")
        ok_cloud, _ = validar_url_externa("https://ryannascimento.app.n8n.cloud/webhook/fryivs-hub")
        assert ok_slack is True
        assert ok_cloud is True

    def test_allows_explicit_n8n_base_url_host_and_port_only(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")

        # Permitido: mesmo host e porta do N8N_BASE_URL
        ok_allowed, reason = validar_url_externa("http://127.0.0.1:5678/webhook/fryivs-hub")
        assert ok_allowed is True, reason

        # Bloqueado: outra porta no mesmo loopback (ex.: servidor interno ou Redis)
        ok_other_port, _ = validar_url_externa("http://127.0.0.1:8000/api/memory")
        assert ok_other_port is False

        # Bloqueado: cloud metadata continua proibido mesmo se passado em allowlist
        ok_meta, _ = validar_url_externa(
            "http://169.254.169.254/latest/meta-data/",
            allowlist_hosts=["169.254.169.254"],
        )
        assert ok_meta is False

    def test_allows_explicit_allowlist_hosts_param(self, monkeypatch):
        monkeypatch.delenv("N8N_BASE_URL", raising=False)
        ok, _ = validar_url_externa(
            "http://n8n-main.internal:5678/webhook/test",
            allowlist_hosts=["n8n-main.internal"],
        )
        assert ok is True

    def test_dns_rebinding_blocked_when_resolve_dns_true(self, monkeypatch):
        monkeypatch.delenv("N8N_BASE_URL", raising=False)
        fake_addrinfo = [(2, 1, 6, "", ("10.0.0.42", 443))]
        with patch("core.n8n_bridge.socket.getaddrinfo", return_value=fake_addrinfo):
            ok, reason = validar_url_externa("https://rebind.attacker.example/hook", resolve_dns=True)
        assert ok is False
        assert "10.0.0.42" in reason


# =============================================================================
# 3. N8nBridge (Webhook, REST API v1, MCP Streamable HTTP) & FastAPI Router
# =============================================================================


class TestN8nBridgeAndRouter:
    def test_trigger_webhook_signs_exact_raw_body(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
        monkeypatch.setenv("N8N_HMAC_SECRET", "chave-super-secreta-n8n")

        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"status": "ok", "message": "Briefing entregue"}

        with patch("core.n8n_bridge.requests.post", return_value=fake_resp) as mock_post:
            bridge = get_n8n_bridge()
            res = bridge.trigger_webhook("briefing", {"topic": "Resumo Diário"}, correlation_id="corr-xyz")

        assert res["ok"] is True
        assert res["signed"] is True
        assert res["correlation_id"] == "corr-xyz"
        assert mock_post.called

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["allow_redirects"] is False
        sent_bytes = call_kwargs["data"]
        sent_headers = call_kwargs["headers"]

        ok_sig, reason = verify_webhook_signature(
            sent_bytes,
            sent_headers[HMAC_HEADER_TIMESTAMP],
            sent_headers[HMAC_HEADER_SIGNATURE],
            "chave-super-secreta-n8n",
        )
        assert ok_sig is True, reason
        parsed_body = json.loads(sent_bytes.decode("utf-8"))
        assert parsed_body["action"] == "briefing"
        assert parsed_body["correlation_id"] == "corr-xyz"
        assert parsed_body["payload"]["topic"] == "Resumo Diário"

    def test_trigger_webhook_blocks_ssrf_without_http_call(self, monkeypatch):
        monkeypatch.delenv("N8N_BASE_URL", raising=False)
        with patch("core.n8n_bridge.requests.post") as mock_post:
            res = get_n8n_bridge().trigger_webhook(
                "alert",
                {"msg": "x"},
                webhook_url="http://169.254.169.254/latest/meta-data/",
            )
        assert res["ok"] is False
        assert "ssrf" in res["error"].lower()
        mock_post.assert_not_called()

    def test_list_workflows_and_executions_rest_api(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
        monkeypatch.setenv("N8N_API_KEY", "n8n-api-test-key")

        wf_resp = MagicMock(status_code=200)
        wf_resp.json.return_value = {
            "data": [
                {
                    "id": "wf-1",
                    "name": "Handle FRYIVS HMAC webhook hub",
                    "active": True,
                    "tags": [{"name": "fryivs"}, {"name": "hmac"}],
                }
            ]
        }
        exec_resp = MagicMock(status_code=200)
        exec_resp.json.return_value = {
            "data": [
                {
                    "id": "99",
                    "workflowId": "wf-1",
                    "status": "success",
                    "mode": "webhook",
                    "startedAt": "2026-11-24T10:00:00Z",
                }
            ]
        }

        with patch("core.n8n_bridge.requests.get", side_effect=[wf_resp, exec_resp]) as mock_get:
            bridge = get_n8n_bridge()
            wfs = bridge.list_workflows(active_only=True, tag="fryivs")
            execs = bridge.list_executions(workflow_id="wf-1", status="success")

        assert wfs["ok"] is True
        assert wfs["count"] == 1
        assert wfs["workflows"][0]["tags"] == ["fryivs", "hmac"]
        assert execs["ok"] is True
        assert execs["executions"][0]["status"] == "success"
        assert mock_get.call_args_list[0].kwargs["headers"]["X-N8N-API-KEY"] == "n8n-api-test-key"

    def test_mcp_streamable_http_sse_parsing(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
        monkeypatch.setenv("N8N_MCP_TOKEN", "mcp-bearer-token")

        sse_resp = MagicMock(status_code=200)
        sse_resp.headers = {"Content-Type": "text/event-stream"}
        sse_resp.text = (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":"1","result":{"tools":[{"name":"fryivs_briefing"}]}}\n\n'
        )

        with patch("core.n8n_bridge.requests.post", return_value=sse_resp) as mock_post:
            res = get_n8n_bridge().mcp_list_tools()

        assert res["ok"] is True
        assert res["count"] == 1
        assert res["tools"][0]["name"] == "fryivs_briefing"
        assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer mcp-bearer-token"

    def test_fastapi_router_e2ee_and_hmac_callback(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
        monkeypatch.setenv("N8N_HMAC_SECRET", "callback-secret-2026")
        monkeypatch.setenv("FRYIVS_VOICE_PASSWORD", "SenhaN8nTest#2026")
        e2ee_auth.reset_e2ee_state(lock_enforcement=True)

        app = FastAPI()
        app.include_router(e2ee_auth.e2ee_router)
        app.include_router(n8n_router)
        client = TestClient(app)

        # 1. Bloqueado sem sessão E2EE -> 423
        assert client.get("/api/n8n/status").status_code == 423
        assert client.get("/api/n8n/workflows").status_code == 423
        assert client.post("/api/n8n/trigger", json={"action": "status"}).status_code == 423

        # 2. Desbloqueio E2EE real -> rotas liberadas
        st = client.get("/api/auth/e2ee/status").json()
        payload, hs_key, _ = e2ee_auth.create_encrypted_unlock_payload(
            "SenhaN8nTest#2026",
            st["server_pubkey_jwk"],
            st["challenge_nonce"],
        )
        unlock_res = client.post("/api/auth/e2ee/unlock", json=payload).json()
        token = e2ee_auth.decrypt_aes_gcm(
            hs_key,
            unlock_res["encrypted_response"]["iv_b64"],
            unlock_res["encrypted_response"]["ciphertext_b64"],
            aad=st["challenge_nonce"].encode("utf-8"),
        )["session_token"]

        status_resp = client.get("/api/n8n/status", headers={"X-E2EE-Session": token})
        assert status_resp.status_code == 200
        assert status_resp.json()["has_hmac_secret"] is True

        # SSRF em /trigger -> 400
        ssrf_resp = client.post(
            "/api/n8n/trigger",
            json={"action": "alert", "webhook_url": "http://169.254.169.254/latest/meta-data/"},
            headers={"X-E2EE-Session": token},
        )
        assert ssrf_resp.status_code == 400

        # 3. POST /api/n8n/callback exige HMAC válido (sem precisar de E2EE, pois é S2S)
        raw_cb = json.dumps({"action": "briefing_done", "status": "ok", "correlation_id": "cb-123"})
        # Sem assinatura -> 401
        assert client.post("/api/n8n/callback", content=raw_cb).status_code == 401

        # Timestamp expirado (>60s) -> 401
        old_headers = sign_webhook_payload(raw_cb, "callback-secret-2026", timestamp=int(time.time()) - 120)
        assert client.post("/api/n8n/callback", content=raw_cb, headers=old_headers).status_code == 401

        # Assinatura válida -> 200
        good_headers = sign_webhook_payload(raw_cb, "callback-secret-2026", correlation_id="cb-123")
        ok_cb = client.post("/api/n8n/callback", content=raw_cb, headers=good_headers)
        assert ok_cb.status_code == 200
        assert ok_cb.json()["status"] == "accepted"
        assert ok_cb.json()["correlation_id"] == "cb-123"
        assert len(get_n8n_bridge().get_recent_callbacks()) == 1

        # Replay do mesmo pacote/nonce -> 401
        replay_cb = client.post("/api/n8n/callback", content=raw_cb, headers=good_headers)
        assert replay_cb.status_code == 401

        # Replay removendo X-Fryivs-Nonce -> 401
        stripped_headers = {k: v for k, v in good_headers.items() if k != HMAC_HEADER_NONCE}
        replay_stripped_cb = client.post("/api/n8n/callback", content=raw_cb, headers=stripped_headers)
        assert replay_stripped_cb.status_code == 401

        # Replay mutando X-Fryivs-Nonce -> 401
        mutated_headers = dict(good_headers)
        mutated_headers[HMAC_HEADER_NONCE] = "mutated-nonce-999999"
        replay_mutated_cb = client.post("/api/n8n/callback", content=raw_cb, headers=mutated_headers)
        assert replay_mutated_cb.status_code == 401

        # Bytes não-UTF-8 sem assinatura válida -> 401 limpo (sem 500)
        bad_bytes_cb = client.post(
            "/api/n8n/callback",
            content=b"\xff\xfe\xfd",
            headers={
                HMAC_HEADER_TIMESTAMP: str(int(time.time())),
                HMAC_HEADER_SIGNATURE: "sha256=" + "0" * 64,
            },
        )
        assert bad_bytes_cb.status_code == 401


# =============================================================================
# 4. Zombie Scheduler Fix & Webhook Hardening em `skills/scheduler_ops.py`
# =============================================================================


class TestSchedulerRehydrationAndWebhookHardening:
    def setup_method(self):
        schedule.clear()
        scheduler_ops._jobs_registry.clear()
        scheduler_ops._scheduler_running = False

    def teardown_method(self):
        schedule.clear()
        scheduler_ops._jobs_registry.clear()
        scheduler_ops._scheduler_running = False

    def test_boot_rehydrates_persisted_jobs_into_schedule_without_duplicates(self, tmp_path):
        jobs_file = tmp_path / "scheduled_jobs.json"
        persisted = [
            {"horario": "08:00", "comando": "Briefing matinal", "tipo": "diario", "criado_em": "2026-11-24 07:00:00"},
            {"horario": "15m", "comando": "Checar alertas n8n", "tipo": "intervalo_minutos", "criado_em": "2026-11-24 07:05:00"},
        ]
        jobs_file.write_text(json.dumps(persisted, ensure_ascii=False), encoding="utf-8")

        with patch.object(scheduler_ops, "_JOBS_FILE", jobs_file):
            assert len(schedule.jobs) == 0
            scheduler_ops._carregar_jobs()

            # Ambos os jobs persistidos foram EFETIVAMENTE registrados em schedule.jobs!
            assert len(scheduler_ops._jobs_registry) == 2
            assert len(schedule.jobs) == 2

            # Chamar _carregar_jobs() novamente NÃO pode duplicar os jobs em schedule.jobs
            scheduler_ops._carregar_jobs()
            assert len(schedule.jobs) == 2

    def test_agendar_execucao_persists_and_avoids_duplicate_schedule_entries(self, tmp_path):
        jobs_file = tmp_path / "scheduled_jobs.json"
        with patch.object(scheduler_ops, "_JOBS_FILE", jobs_file), patch.object(
            scheduler_ops, "_garantir_scheduler_ativo", lambda: None
        ):
            r1 = scheduler_ops.agendar_execucao("09:30", "Enviar resumo executivo", "diario")
            r2 = scheduler_ops.agendar_execucao("09:30", "Enviar resumo executivo", "diario")

        assert "agendada" in r1.lower()
        assert "agendada" in r2.lower()
        assert len(schedule.jobs) == 1
        assert len(scheduler_ops._jobs_registry) == 1
        saved = json.loads(jobs_file.read_text(encoding="utf-8"))
        assert len(saved) == 1

    def test_enviar_alerta_webhook_blocks_ssrf_and_signs_hmac(self, monkeypatch):
        monkeypatch.delenv("N8N_BASE_URL", raising=False)
        monkeypatch.setenv("N8N_HMAC_SECRET", "webhook-secret-999")

        # SSRF bloqueado sem chamar requests.post
        with patch("skills.scheduler_ops.requests.post") as mock_post:
            r_meta = scheduler_ops.enviar_alerta_webhook("teste", "http://169.254.169.254/latest/meta-data/")
            r_lan = scheduler_ops.enviar_alerta_webhook("teste", "https://10.0.0.1/internal")
            r_file = scheduler_ops.enviar_alerta_webhook("teste", "file:///etc/passwd")
            assert "ssrf" in r_meta.lower()
            assert "ssrf" in r_lan.lower()
            assert "ssrf" in r_file.lower()
            mock_post.assert_not_called()

        # HTTPS público permitido e assinado com HMAC-SHA256
        fake_ok = MagicMock(status_code=200, text="ok")
        with patch("skills.scheduler_ops.requests.post", return_value=fake_ok) as mock_post:
            r_ok = scheduler_ops.enviar_alerta_webhook(
                "Servidor saudável",
                webhook_url="https://hooks.slack.com/services/T00/B00/XYZ",
                servico="Slack",
            )

        assert "sucesso" in r_ok.lower()
        assert "hmac-sha256" in r_ok.lower()
        kwargs = mock_post.call_args.kwargs
        ok_sig, _ = verify_webhook_signature(
            kwargs["data"],
            kwargs["headers"][HMAC_HEADER_TIMESTAMP],
            kwargs["headers"][HMAC_HEADER_SIGNATURE],
            "webhook-secret-999",
        )
        assert ok_sig is True


# =============================================================================
# 5. Skills n8n (`skills/n8n_ops.py`) & Docker Compose Sanity Check
# =============================================================================


class TestN8nSkillsAndInfra:
    def test_n8n_schemas_structure(self):
        names = [s["function"]["name"] for s in n8n_ops.N8N_SCHEMAS]
        assert names == [
            "disparar_workflow_n8n",
            "listar_workflows_n8n",
            "consultar_execucoes_n8n",
        ]
        for schema in n8n_ops.N8N_SCHEMAS:
            assert schema["type"] == "function"
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    def test_disparar_workflow_n8n_with_dict_and_json_string(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
        monkeypatch.setenv("N8N_HMAC_SECRET", "skills-secret")

        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"status": "ok", "message": "Briefing processado"}

        with patch("core.n8n_bridge.requests.post", return_value=fake_resp):
            out1 = n8n_ops.disparar_workflow_n8n("briefing", {"topic": "Vendas"})
            out2 = n8n_ops.disparar_workflow_n8n("alert", '{"severity":"high"}')

        assert "sucesso" in out1.lower()
        assert "hmac-sha256" in out1.lower()
        assert "briefing processado" in out1.lower()
        assert "sucesso" in out2.lower()

    def test_listar_workflows_and_consultar_execucoes_skills(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
        monkeypatch.setenv("N8N_API_KEY", "test-key")

        wf_resp = MagicMock(status_code=200)
        wf_resp.json.return_value = {
            "data": [{"id": "wf-42", "name": "Summarize FRYIVS daily executive briefing", "active": False, "tags": [{"name": "fryivs"}]}]
        }
        exec_resp = MagicMock(status_code=200)
        exec_resp.json.return_value = {
            "data": [{"id": "101", "workflowId": "wf-42", "status": "success", "startedAt": "2026-11-24T08:00:00Z"}]
        }

        with patch("core.n8n_bridge.requests.get", side_effect=[wf_resp, exec_resp]):
            wf_out = n8n_ops.listar_workflows_n8n(tag="fryivs")
            ex_out = n8n_ops.consultar_execucoes_n8n(workflow_id="wf-42", status="success")

        assert "Summarize FRYIVS daily executive briefing" in wf_out
        assert "wf-42" in wf_out
        assert "Execução #101" in ex_out

    def test_invalid_pydantic_args_return_clean_error(self):
        out = n8n_ops.consultar_execucoes_n8n(status="invalido")
        assert "erro" in out.lower()

    def test_docker_compose_n8n_stack_valid_and_pinned(self):
        compose_path = ROOT / "infra" / "docker-compose.n8n.yml"
        assert compose_path.exists()
        content = compose_path.read_text(encoding="utf-8")
        for required_token in (
            "n8n-main:",
            "n8n-worker:",
            "postgres:16-alpine",
            "redis:7-alpine",
            "127.0.0.1:${N8N_PORT:-5678}:5678",
            "EXECUTIONS_MODE: queue",
            "healthcheck:",
            "N8N_HMAC_SECRET",
        ):
            assert required_token in content, f"Faltando '{required_token}' em infra/docker-compose.n8n.yml"
