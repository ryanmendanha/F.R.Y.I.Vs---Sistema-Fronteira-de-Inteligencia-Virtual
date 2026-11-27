"""
Testes automatizados da migração F.R.Y.I.Vs Web Mode (Dual-Mode Desktop + Cloud/Railway):
- Isolamento de paths em volume persistente (FRYIVS_DATA_DIR / RAILWAY_VOLUME_MOUNT_PATH)
- Healthcheck público (/health) independente de bloqueio E2EE
- Isolamento estrito de sessão E2EE em modo Web público (sem vazamento global para terceiros)
- Filtragem de skills Desktop-only vs Cloud-safe e workspace seguro de upload/download (.xlsx/.docx)
- Endpoint WebAudio STT (/api/voice/transcribe) com áudio por requisição (/api/audio/resp_*)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _unlock_client_session(client: TestClient, password: str) -> tuple[str, bytes]:
    from core.e2ee_auth import create_encrypted_unlock_payload, decrypt_aes_gcm

    ch = client.get("/api/auth/e2ee/status")
    assert ch.status_code == 200
    ch_data = ch.json()
    nonce = ch_data["challenge_nonce"]
    unlock_payload, handshake_key, session_key = create_encrypted_unlock_payload(
        password=password,
        server_pubkey_jwk=ch_data["server_pubkey_jwk"],
        challenge_nonce=nonce,
    )
    res = client.post("/api/auth/e2ee/unlock", json=unlock_payload)
    assert res.status_code == 200, res.text
    enc_resp = res.json()["encrypted_response"]
    dec = decrypt_aes_gcm(
        handshake_key,
        enc_resp["iv_b64"],
        enc_resp["ciphertext_b64"],
        aad=nonce.encode("utf-8"),
    )
    return dec["session_token"], session_key


def test_runtime_mode_and_volume_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from core import runtime_mode

    monkeypatch.delenv("FRYIVS_MODE", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    assert runtime_mode.get_runtime_mode() == "desktop"
    assert not runtime_mode.is_web_mode()

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert runtime_mode.get_runtime_mode() == "web"
    assert runtime_mode.is_web_mode()

    vol = tmp_path / "railway_data"
    monkeypatch.setenv("FRYIVS_MODE", "web")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(vol))
    monkeypatch.delenv("FRYIVS_DATA_DIR", raising=False)

    assert runtime_mode.get_data_dir() == vol.resolve()
    assert runtime_mode.get_chroma_dir() == vol.resolve() / "fryvis_memory"
    assert runtime_mode.get_sessions_db_path() == vol.resolve() / "data" / "sessions.db"
    assert runtime_mode.get_audio_cache_dir() == vol.resolve() / "audio_cache"
    assert runtime_mode.get_files_workspace_dir() == vol.resolve() / "arquivos_fryivs"


def test_healthcheck_and_public_e2ee_isolation_in_web_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core import e2ee_auth
    import server

    pw = "Fryivs#WebSecret2026"
    pw_hash = e2ee_auth.hash_password(pw, iterations=100_000)

    monkeypatch.setenv("FRYIVS_MODE", "web")
    monkeypatch.setenv("FRYIVS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRYIVS_REQUIRE_E2EE_PASSWORD", "true")
    monkeypatch.setenv("FRYIVS_VOICE_PASSWORD_HASH", pw_hash)
    monkeypatch.delenv("FRYIVS_VOICE_PASSWORD", raising=False)
    e2ee_auth.reset_e2ee_state(lock_enforcement=True)

    client = TestClient(server.app)

    # 1. Healthcheck do Railway deve responder 200 mesmo com E2EE trancado
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json() == {"status": "ok", "mode": "web"}

    r_status = client.get("/api/status")
    assert r_status.status_code == 200
    assert r_status.json()["runtime_mode"] == "web"

    # 2. Dono autentica com sua senha no dispositivo A
    owner_token, _ = _unlock_client_session(client, pw)
    owner_headers = {"X-E2EE-Session": owner_token, "X-Forwarded-For": "198.51.100.10"}

    st_owner = client.get("/api/auth/e2ee/status", headers=owner_headers)
    assert st_owner.status_code == 200
    assert st_owner.json()["unlocked"] is True
    assert st_owner.json()["session_valid"] is True

    # 3. Visitante desconhecido (sem token) NÃO vê a IA destrancada e recebe 423
    stranger_headers = {"X-Forwarded-For": "203.0.113.99"}
    st_stranger = client.get("/api/auth/e2ee/status", headers=stranger_headers)
    assert st_stranger.status_code == 200
    assert st_stranger.json()["unlocked"] is False
    assert st_stranger.json()["session_valid"] is False

    assert client.post("/api/chat", json={"message": "oi"}, headers=stranger_headers).status_code == 423
    assert client.get("/api/files", headers=stranger_headers).status_code == 423
    assert client.get("/api/agents/status", headers=stranger_headers).status_code == 423

    # 4. Visitante sem token chamar /lock NÃO derruba a sessão autenticada do dono
    client.post("/api/auth/e2ee/lock", headers=stranger_headers)
    st_owner_after = client.get("/api/auth/e2ee/status", headers=owner_headers)
    assert st_owner_after.json()["unlocked"] is True
    assert st_owner_after.json()["session_valid"] is True

    e2ee_auth.reset_e2ee_state(lock_enforcement=None)


def test_web_mode_skill_filtering_and_workspace_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core import e2ee_auth
    from skills import execute_skill
    import server

    monkeypatch.setenv("FRYIVS_MODE", "web")
    monkeypatch.setenv("FRYIVS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRYIVS_REQUIRE_E2EE_PASSWORD", "false")
    e2ee_auth.reset_e2ee_state(lock_enforcement=False)

    client = TestClient(server.app)

    # Skills GUI/Windows ocultadas em modo Web, skills Cloud mantidas
    sk_resp = client.get("/api/skills")
    assert sk_resp.status_code == 200
    active_skills = set(sk_resp.json()["skills"])
    assert "abrir_programa" not in active_skills
    assert "tirar_screenshot" not in active_skills
    assert "clicar_mouse" not in active_skills
    assert "criar_planilha" in active_skills
    assert "criar_documento_word" in active_skills
    assert "pesquisar_informacao_web" in active_skills
    assert "delegar_missao_hermes" in active_skills

    # Execução direta de skill Desktop bloqueada com mensagem amigável
    res_gui = execute_skill("abrir_programa", {"nome": "notepad"})
    assert "indisponível na versão Web Cloud" in res_gui

    # Criação de planilha em nuvem salva no volume e retorna link de download
    res_xlsx = execute_skill(
        "criar_planilha",
        {
            "caminho_arquivo": "custos_cloud",
            "colunas": ["Servico", "Mensal"],
            "dados": [["Railway", 25], ["Dominio", 5]],
        },
    )
    assert "/api/files/download/custos_cloud.xlsx" in res_xlsx
    saved_xlsx = tmp_path / "arquivos_fryivs" / "custos_cloud.xlsx"
    assert saved_xlsx.exists() and saved_xlsx.stat().st_size > 0

    # Listagem e download seguro
    files_list = client.get("/api/files").json()["files"]
    assert any(f["name"] == "custos_cloud.xlsx" for f in files_list)

    dl_ok = client.get("/api/files/download/custos_cloud.xlsx")
    assert dl_ok.status_code == 200
    assert len(dl_ok.content) == saved_xlsx.stat().st_size

    # Bloqueio de tentativa de path traversal
    dl_bad = client.get("/api/files/download/..%5Cserver.py")
    assert dl_bad.status_code in (400, 404)

    # Upload válido (.csv) vs formato proibido (.exe)
    up_ok = client.post(
        "/api/files/upload?filename=dados_clientes.csv",
        content=b"nome,valor\nAna,100\n",
        headers={"Content-Type": "text/csv"},
    )
    assert up_ok.status_code == 200
    assert (tmp_path / "arquivos_fryivs" / "dados_clientes.csv").exists()

    up_bad = client.post(
        "/api/files/upload?filename=malware.exe",
        content=b"MZ1234",
    )
    assert up_bad.status_code == 400


def test_web_voice_transcribe_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core import e2ee_auth
    import server

    monkeypatch.setenv("FRYIVS_MODE", "web")
    monkeypatch.setenv("FRYIVS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRYIVS_REQUIRE_E2EE_PASSWORD", "false")
    e2ee_auth.reset_e2ee_state(lock_enforcement=False)

    monkeypatch.setattr(
        server,
        "transcribe_audio_gemini",
        lambda audio_bytes, mime_type="audio/webm": "status rapido da memoria",
    )
    monkeypatch.setattr(
        server,
        "ask_fryvis",
        lambda **kwargs: ("Memória operacional estável na nuvem, senhor.", []),
    )

    def _fake_falar(texto: str, output_path: str = "resposta.mp3") -> str:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ID3FAKEAUDIO" * 20)
        return str(p)

    monkeypatch.setattr(server, "falar", _fake_falar)

    client = TestClient(server.app)
    res = client.post(
        "/api/voice/transcribe?profile=fryvis_1.0&provider=gemini",
        content=b"WEBM_OPUS_AUDIO_BYTES_" * 10,
        headers={"Content-Type": "audio/webm"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["transcription"] == "status rapido da memoria"
    assert "estável na nuvem" in payload["response"]
    assert payload["played_locally"] is False
    assert payload["has_audio"] is True
    assert payload["audio_url"].startswith("/api/audio/resp_")

    audio_res = client.get(payload["audio_url"])
    assert audio_res.status_code == 200
    assert audio_res.content.startswith(b"ID3FAKEAUDIO")

