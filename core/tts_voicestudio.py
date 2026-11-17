"""
Integrador VoiceStudio TTS para F.R.Y.I.Vs.

Conecta ao backend local do VoiceStudio (OmniVoice) como provedor TTS premium,
com suporte a clonagem de voz, design de voz e 646+ linguas.

O VoiceStudio deve estar rodando localmente (app Electron ou servidor Python).
Endpoint compativel com OpenAI: POST /v1/audio/speech

Configuracao via .env:
    TTS_PROVIDER=voicestudio
    VOICESTUDIO_URL=http://127.0.0.1:PORT
    VOICESTUDIO_VOICE=default
    VOICESTUDIO_MODEL=omnivoice
"""

from __future__ import annotations

import os
import json
import uuid
import threading
from pathlib import Path
from urllib import request, error

_DEFAULT_PORT = 3900
_TTS_LOCK = threading.Lock()


def _get_base_url() -> str:
    explicit = os.getenv("VOICESTUDIO_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    port_env = os.getenv("OMNIVOICE_PORT", "").strip()
    if port_env:
        try:
            port = int(port_env)
            if 0 < port <= 65535:
                return f"http://127.0.0.1:{port}"
        except ValueError:
            pass
    return f"http://127.0.0.1:{_DEFAULT_PORT}"


def _check_voicestudio_alive(base_url: str, timeout: float = 2.0) -> bool:
    for endpoint in ["/.well-known/voicestudio-speech", "/v1/models", "/health"]:
        try:
            req = request.Request(
                f"{base_url}{endpoint}",
                headers={"Accept": "application/json"}
            )
            with request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
    return False


def falar_voicestudio(texto: str, output_path: str) -> str:
    if not texto or not texto.strip():
        return ""

    base_url = _get_base_url()
    if not _check_voicestudio_alive(base_url):
        print(
            f"[TTS-VoiceStudio] Servidor nao acessivel em {base_url}. "
            "Inicie o VoiceStudio (app Electron ou 'bun run dev' na pasta VoiceStudio)."
        )
        return ""

    voice = os.getenv("VOICESTUDIO_VOICE", "fryivs").strip() or "fryivs"
    model = os.getenv("VOICESTUDIO_MODEL", "omnivoice").strip() or "omnivoice"
    timeout_s = float(os.getenv("VOICESTUDIO_TIMEOUT", "180"))
    payload = {
        "model": model,
        "input": texto.strip(),
        "voice": voice,
        "response_format": "mp3",
    }
    temp_path = f"{output_path}.vs_tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"

    with _TTS_LOCK:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                f"{base_url}/v1/audio/speech",
                data=data,
                headers={"Content-Type": "application/json", "Accept": "audio/mpeg, audio/*, */*"},
                method="POST",
            )
            with request.urlopen(req, timeout=timeout_s) as resp:
                audio_bytes = resp.read()

            if not audio_bytes:
                print("[TTS-VoiceStudio] Resposta vazia do servidor.")
                return ""

            Path(temp_path).write_bytes(audio_bytes)
            if os.path.getsize(temp_path) > 0:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                os.replace(temp_path, output_path)
                sz = os.path.getsize(output_path)
                print(f"[TTS-VoiceStudio] Audio gerado (modelo: {model}, voz: {voice}) -> {output_path} ({sz} bytes)")
                return output_path
            return ""

        except error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            print(f"[TTS-VoiceStudio] HTTP {e.code}: {body or e.reason}")
            return ""
        except error.URLError as e:
            print(f"[TTS-VoiceStudio] Falha de conexao: {e.reason}")
            return ""
        except Exception as e:
            print(f"[TTS-VoiceStudio] Erro inesperado: {e}")
            return ""
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


def voicestudio_disponivel() -> bool:
    return _check_voicestudio_alive(_get_base_url())


def listar_vozes_voicestudio() -> list:
    base_url = _get_base_url()
    for endpoint in ["/v1/audio/voices", "/profiles"]:
        try:
            req = request.Request(
                f"{base_url}{endpoint}",
                headers={"Accept": "application/json"}
            )
            with request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, list) else data.get("voices", [])
        except Exception:
            continue
    return []
