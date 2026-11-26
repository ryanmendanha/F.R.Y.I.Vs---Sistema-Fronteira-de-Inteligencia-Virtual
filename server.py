"""
Servidor Backend FastAPI da assistente F.R.Y.I.Vs.
Implementa rotas REST, WebSocket em tempo real, integração com ChromaDB, Whisper e Ollama.
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"chromadb.*")
warnings.filterwarnings("ignore", message=r".*asyncio\.iscoroutinefunction.*", category=DeprecationWarning)
try:
    from starlette.exceptions import StarletteDeprecationWarning
    warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)
except ImportError:
    pass

import random

from contextlib import asynccontextmanager

import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_stdin = kernel32.GetStdHandle(-10)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE = 0x0040
            ENABLE_EXTENDED_FLAGS = 0x0080
            new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
            kernel32.SetConsoleMode(h_stdin, new_mode)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import asyncio
import hmac
from typing import Any
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from core.e2ee_auth import (
    E2EESessionRecord,
    decrypt_chat_envelope,
    e2ee_router,
    encrypt_chat_envelope,
    extract_e2ee_token,
    is_e2ee_required,
    is_session_unlocked,
    register_on_lock_callback,
    require_e2ee_session,
    validate_session_token,
)

_API_TOKEN: str = os.getenv("FRYIVS_API_TOKEN", "")


def _verificar_token(authorization: str = Header(default="")) -> None:
    """Dependência FastAPI: valida Bearer token via hmac.compare_digest (timing-safe).
    Se FRYIVS_API_TOKEN não estiver configurado, a verificação é ignorada (modo dev).
    """
    if not _API_TOKEN:
        return
    partes = authorization.split(" ", 1)
    token_recebido = partes[1] if len(partes) == 2 and partes[0].lower() == "bearer" else ""
    if not hmac.compare_digest(
        token_recebido.encode("utf-8"),
        _API_TOKEN.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Token inválido ou ausente.")


from core.llm import ask_fryvis, MODEL, MODEL_PROFILES, DEFAULT_PROFILE, LLM_PROVIDER
from core.gemini_client import is_gemini_configured, is_gemini_online
from core.memory import salvar_memoria, buscar_contexto, listar_memorias, deletar_memoria
from core.skill_router import get_skill_router
from core.stt import gravar_audio, transcrever
from core.tts import falar
from core.vector_db import get_or_create_collection
from core.knowledge_base import (
    buscar_conhecimento,
    indexar as kb_indexar,
    listar_documentos_conhecimento,
    status as kb_status,
)
from skills import ALL_SKILL_SCHEMAS, SKILLS_REGISTRY, execute_skill

_server_loop: asyncio.AbstractEventLoop | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Aquece o roteador de skills, memória, base de conhecimento e o modelo Ollama no startup."""
    global _server_loop
    _server_loop = asyncio.get_running_loop()
    try:
        router = get_skill_router()
        router.ensure_skills_indexed()
        print("[Startup] Skills indexadas com sucesso no ChromaDB.")
    except Exception as e:
        print(f"[Startup] Aviso ao inicializar banco vetorial: {e}")

    try:
        novos = kb_indexar(forcar=False, verbose=True)
        info = kb_status()
        print(f"[Startup] Base de conhecimento: {info.get('count', 0)} chunks indexados ({novos} novos).")
    except Exception as e:
        print(f"[Startup] Aviso ao indexar base de conhecimento: {e}")

    try:
        import requests as _req
        _req.post(
            "http://localhost:11434/api/generate",
            json={"model": MODEL, "prompt": "", "keep_alive": -1, "stream": False},
            timeout=60,
        )
        print(f"[Startup] Modelo '{MODEL}' aquecido e mantido em memória (keep_alive=-1).")
    except Exception as e:
        print(f"[Startup] Aviso: não foi possível aquecer o modelo Ollama: {e}")

    try:
        from core.overlay import iniciar_overlay
        iniciar_overlay()
        print("[Startup] Barra flutuante da FRYIVS ativa.")
    except Exception as e:
        print(f"[Startup] Aviso: barra flutuante indisponível: {e}")

    try:
        from core import voice_daemon
        loop_atual = asyncio.get_running_loop()
        if voice_daemon.iniciar(loop_atual, manager.broadcast):
            print("[Startup] VoiceDaemon de Wake Word ('FRYIVS/Frives') ativo no servidor.")
    except Exception as e:
        print(f"[Startup] Aviso ao iniciar VoiceDaemon: {e}")

    if not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from skills.scheduler_ops import _garantir_scheduler_ativo
            _garantir_scheduler_ativo()
            print("[Startup] Scheduler persistente da FRYIVS ativo.")
        except Exception as e:
            print(f"[Startup] Aviso ao iniciar Scheduler: {e}")

    yield
    from core.command_queue import get_queue
    from core.audio_player import parar as parar_audio
    parar_audio()
    await get_queue().close()
    try:
        from core import voice_daemon
        voice_daemon.parar()
    except Exception:
        pass
    try:
        from core.overlay import parar_overlay
        parar_overlay()
    except Exception:
        pass


app = FastAPI(
    title="F.R.Y.I.Vs AI Assistant",
    description="Interface e Backend do assistente inteligente neural F.R.Y.I.Vs",
    version="1.2.0",
    lifespan=lifespan
)

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra_cors = [
    origin.strip()
    for origin in os.getenv("FRYIVS_CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_CORS_ORIGINS + _extra_cors,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-E2EE-Session"],
)

app.include_router(e2ee_router)

try:
    from core.opencode_brain import brain_router
    app.include_router(brain_router)
except ImportError:
    pass

from core.n8n_bridge import n8n_router
from core.agent_orchestrator import agents_router

app.include_router(n8n_router)
app.include_router(agents_router)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "ui", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ConnectionManager:
    """Gerenciador de conexões WebSocket ativas."""
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

    async def close_all_locked(self) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json({"type": "e2ee_locked", "unlocked": False})
            except Exception:
                pass
            try:
                await connection.close(code=4423, reason="F.R.Y.I.Vs bloqueada (E2EE)")
            except Exception:
                pass
            if connection in self.active_connections:
                self.active_connections.remove(connection)


manager = ConnectionManager()


def _on_e2ee_lock() -> None:
    try:
        from core import voice_daemon
        if voice_daemon._daemon_instance is not None:
            voice_daemon._daemon_instance._resetar_captura()
            voice_daemon._daemon_instance._mudar_estado("DORMINDO")
    except Exception:
        pass
    try:
        loop = _server_loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.close_all_locked(), loop)
    except Exception:
        pass


register_on_lock_callback(_on_e2ee_lock)


class E2EEEnvelope(BaseModel):
    iv_b64: str = Field(..., min_length=12, description="IV AES-256-GCM (96 bits) em base64")
    ciphertext_b64: str = Field(..., min_length=16, description="Ciphertext + tag GCM em base64")


class ChatRequest(BaseModel):
    message: str | None = Field(default=None, description="Mensagem de texto do usuário")
    e2ee: E2EEEnvelope | None = Field(default=None, description="Envelope AES-256-GCM opcional cifrado com a chave de sessão")
    use_memory: bool = Field(default=True, description="Se deve consultar e persistir memória semântica")
    generate_speech: bool = Field(default=True, description="Se deve gerar áudio com voz (TTS)")
    history: list[dict[str, str]] = Field(default_factory=list, description="Histórico prévio de mensagens")
    model_profile: str = Field(default=DEFAULT_PROFILE, description="Perfil de tokens: fryvis_beta (40), fryvis_1.0 (50), fryvis_recursive (80)")
    provider: str | None = Field(default=None, description="Provedor LLM: hybrid, ollama, gemini")

    @model_validator(mode="after")
    def _validate_message_or_e2ee(self) -> "ChatRequest":
        if self.e2ee is None:
            if self.message is None or len(self.message) < 1:
                raise ValueError("Campo 'message' deve ter pelo menos 1 caractere ou enviar envelope 'e2ee'.")
        return self


class SkillExecuteRequest(BaseModel):
    skill: str = Field(..., description="Nome da skill a ser executada")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Argumentos da skill")


@app.get("/")
def get_ui() -> Any:
    """Retorna a interface visual principal."""
    index_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Interface ui/index.html não encontrada."}


@app.get("/graph")
def get_graph_ui() -> Any:
    """Retorna a interface interativa do mapa arquitetural gerado pelo Graphify."""
    graph_path = os.path.join(os.path.dirname(__file__), "graphify-out", "graph.html")
    if os.path.exists(graph_path):
        return FileResponse(graph_path, media_type="text/html")
    return {"message": "Grafo arquitetural graphify-out/graph.html não encontrado."}


@app.get("/graph/tree")
def get_graph_tree_ui() -> Any:
    """Retorna a visualização em árvore colapsável D3 da arquitetura do sistema."""
    tree_path = os.path.join(os.path.dirname(__file__), "graphify-out", "GRAPH_TREE.html")
    if os.path.exists(tree_path):
        return FileResponse(tree_path, media_type="text/html")
    return {"message": "Árvore arquitetural graphify-out/GRAPH_TREE.html não encontrada."}


@app.get("/health")
@app.get("/api/status")
def get_system_status() -> dict[str, Any]:
    """Retorna o estado de prontidão dos módulos, banco vetorial e modelos."""
    ollama_ok = False
    ollama_error = None
    try:
        import requests
        res = requests.get("http://localhost:11434/api/tags", timeout=2)
        if res.status_code == 200:
            ollama_ok = True
    except Exception as e:
        ollama_error = str(e)

    mem_count = 0
    skills_indexed = 0
    try:
        mem_col = get_or_create_collection("fryvis_memoria")
        mem_count = mem_col.count()
        skills_col = get_or_create_collection("fryvis_skills_v2")
        skills_indexed = skills_col.count()
    except Exception:
        pass

    try:
        from core import voice_daemon
        from core.session_state import obter_artefato
        daemon_info = voice_daemon.status()
        artefato = obter_artefato()
    except Exception:
        daemon_info = {"active": False, "state": "INATIVO"}
        artefato = None

    return {
        "status": "online",
        "assistant_name": "F.R.Y.I.Vs",
        "model": MODEL,
        "default_profile": DEFAULT_PROFILE,
        "available_profiles": list(MODEL_PROFILES.values()),
        "llm_provider": LLM_PROVIDER,
        "ollama_online": ollama_ok,
        "ollama_error": ollama_error,
        "gemini_configured": is_gemini_configured(),
        "gemini_online": is_gemini_online(),
        "memory_count": mem_count,
        "skills_indexed_count": skills_indexed,
        "skills_count": len(SKILLS_REGISTRY),
        "available_skills": list(SKILLS_REGISTRY.keys()),
        "voice_daemon": daemon_info,
        "voice_daemon_active": daemon_info.get("active", False),
        "mic_muted": daemon_info.get("muted", False),
        "active_artifact": artefato,
        "e2ee_required": is_e2ee_required(),
        "e2ee_unlocked": is_session_unlocked(),
    }


_FRASES_ANALISANDO = [
    "Analisando comando, senhor.",
    "Recebido, senhor. Processando agora.",
    "Entendido, senhor. Executando análise.",
    "Comando recebido. Iniciando processamento, senhor.",
    "Certo, senhor. Analisando sua solicitação.",
]

_FRASES_ERRO = [
    "Protocolo falhou, senhor. Não consegui processar sua solicitação.",
    "Desculpe, senhor. Ocorreu uma falha no sistema durante a execução.",
    "Senhor, encontrei um erro crítico. O protocolo não pôde ser concluído.",
    "Falha no núcleo, senhor. O comando não foi executado com sucesso.",
    "Lamento, senhor. Houve uma anomalia inesperada no processamento.",
    "Sistema comprometido, senhor. Não foi possível completar a operação.",
    "Aviso de erro, senhor. O protocolo foi interrompido inesperadamente.",
]


@app.post("/api/chat")
async def process_chat(
    req: ChatRequest,
    _auth: None = Depends(_verificar_token),
    e2ee_session: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Processa uma mensagem de texto com IA (suporta transporte opcional E2EE AES-256-GCM)."""
    loop = asyncio.get_event_loop()
    use_encrypted_transport = req.e2ee is not None

    message_text = req.message or ""
    use_memory = req.use_memory
    generate_speech = req.generate_speech
    history = req.history
    model_profile = req.model_profile
    provider = req.provider

    if use_encrypted_transport:
        if e2ee_session is None:
            raise HTTPException(
                status_code=423,
                detail="Sessão E2EE válida obrigatória para transporte criptografado.",
            )
        decrypted = decrypt_chat_envelope(
            e2ee_session,
            req.e2ee.iv_b64,
            req.e2ee.ciphertext_b64,
        )
        message_text = str(decrypted.get("message", ""))
        if len(message_text) < 1:
            raise HTTPException(status_code=422, detail="Mensagem descriptografada não pode ser vazia.")
        use_memory = bool(decrypted.get("use_memory", use_memory))
        generate_speech = bool(decrypted.get("generate_speech", generate_speech))
        if isinstance(decrypted.get("history"), list):
            history = decrypted["history"]
        if isinstance(decrypted.get("model_profile"), str) and decrypted["model_profile"]:
            model_profile = decrypted["model_profile"]
        if "provider" in decrypted:
            provider = decrypted["provider"]

    try:
        from core.assistant_pipeline import processar_comando
        res = await processar_comando(
            texto=message_text,
            origem="chat",
            profile=model_profile,
            provider=provider,
            use_memory=use_memory,
            generate_speech=generate_speech,
            history=history,
            tocar_local=False,
            broadcast_fn=manager.broadcast,
            buscar_contexto_fn=buscar_contexto,
            buscar_conhecimento_fn=buscar_conhecimento,
            ask_fryvis_fn=ask_fryvis,
            salvar_memoria_fn=salvar_memoria,
            falar_fn=falar,
        )
        payload = {
            "command_id": res.get("command_id"),
            "cancelled": res.get("cancelled", False),
            "user_message": message_text,
            "response": res["response"],
            "context_used": res["context_used"],
            "tools_executed": res["tools_executed"],
            "has_audio": res["has_audio"],
            "audio_url": res["audio_url"],
            "played_locally": res["played_locally"],
        }
        if use_encrypted_transport and e2ee_session is not None:
            return {
                "encrypted": True,
                "e2ee": encrypt_chat_envelope(e2ee_session, payload),
            }
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        _err = random.choice(_FRASES_ERRO)
        asyncio.ensure_future(loop.run_in_executor(None, lambda: falar(_err, output_path="erro.mp3")))
        await manager.broadcast({"type": "state_change", "state": "idle", "detail": "Erro"})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/voice/listen")
async def voice_listen(
    duration: int = Query(5, ge=1, le=60),
    profile: str = Query(DEFAULT_PROFILE, description="Perfil de tokens: fryvis_beta (40), fryvis_1.0 (50), fryvis_recursive (80)"),
    provider: str | None = Query(None, description="Provedor LLM: hybrid, ollama, gemini"),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Grava áudio do microfone, transcreve com Whisper e processa na F.R.Y.I.Vs."""
    loop = asyncio.get_event_loop()

    await manager.broadcast({
        "type": "state_change",
        "state": "listening",
        "detail": f"Ouvindo microfone ({duration}s)..."
    })

    audio, fs = await loop.run_in_executor(None, lambda: gravar_audio(duracao=duration))

    if len(audio) == 0:
        await manager.broadcast({"type": "state_change", "state": "idle", "detail": "Nenhum áudio detectado."})
        raise HTTPException(status_code=400, detail="Não foi possível capturar o áudio do microfone.")

    await manager.broadcast({
        "type": "state_change",
        "state": "thinking",
        "detail": "Transcrevendo voz com Whisper..."
    })
    texto_usuario = await loop.run_in_executor(None, lambda: transcrever(audio, fs))

    if not texto_usuario:
        sem_fala = "Não consegui entender com clareza, senhor. Pode repetir?"
        await loop.run_in_executor(None, lambda: falar(sem_fala, output_path="resposta.mp3"))
        await manager.broadcast({"type": "state_change", "state": "idle", "detail": "Nenhuma fala detectada."})
        return {
            "transcription": "",
            "response": sem_fala,
            "tools_executed": [],
            "has_audio": True,
            "played_locally": False,
        }

    try:
        from core.assistant_pipeline import processar_comando
        res = await processar_comando(
            texto=texto_usuario,
            origem="voz",
            profile=profile,
            provider=provider,
            use_memory=True,
            generate_speech=True,
            broadcast_fn=manager.broadcast,
            buscar_contexto_fn=buscar_contexto,
            buscar_conhecimento_fn=buscar_conhecimento,
            ask_fryvis_fn=ask_fryvis,
            salvar_memoria_fn=salvar_memoria,
            falar_fn=falar,
        )
        return {
            "transcription": texto_usuario,
            "response": res["response"],
            "context_used": res["context_used"],
            "tools_executed": res["tools_executed"],
            "has_audio": res["has_audio"],
            "audio_url": res["audio_url"],
            "played_locally": res["played_locally"],
        }
    except Exception as exc:
        frase_erro = random.choice(_FRASES_ERRO)
        await loop.run_in_executor(None, lambda: falar(frase_erro, output_path="erro.mp3"))
        await manager.broadcast({"type": "state_change", "state": "idle", "detail": "Erro"})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class VoiceDaemonRequest(BaseModel):
    enabled: bool = Field(..., description="Ativa ou desativa a escuta contínua por wake word")


@app.get("/api/voice/daemon")
def get_voice_daemon_status() -> dict[str, Any]:
    """Retorna o estado atual do daemon de escuta contínua e o artefato ativo."""
    from core import voice_daemon
    from core.session_state import obter_artefato
    st = voice_daemon.status()
    st["active_artifact"] = obter_artefato()
    return st


@app.post("/api/voice/daemon")
async def set_voice_daemon_status(
    req: VoiceDaemonRequest,
    _auth: None = Depends(_verificar_token),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Liga ou desliga a escuta contínua por wake word no servidor."""
    from core import voice_daemon
    if req.enabled:
        loop_atual = asyncio.get_running_loop()
        voice_daemon.iniciar(loop_atual, manager.broadcast)
    else:
        voice_daemon.parar()
    st = voice_daemon.status()
    await manager.broadcast({"type": "voice_daemon_status", **st})
    return st


@app.post("/api/voice/trigger")
async def trigger_voice_wake(
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Aciona manualmente o modo 'Senhor?' do daemon de voz (botão de microfone)."""
    from core import voice_daemon
    acionado = voice_daemon.acionar_manual()
    return {"triggered": acionado, **voice_daemon.status()}


class MicMuteRequest(BaseModel):
    muted: bool = Field(..., description="True = mutar microfone e voz; False = desmutar")


@app.post("/api/voice/mute")
async def set_mic_mute(
    req: MicMuteRequest,
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """
    Muta ou desmuta o sistema de voz sem encerrar o VoiceDaemon.
    Quando mutado: microfone descartado + TTS/áudio bloqueados.
    Ao desmutar, o daemon retoma a escuta por wake word.
    """
    from core import voice_daemon
    voice_daemon.set_muted(req.muted)
    st = voice_daemon.status()
    await manager.broadcast({"type": "mic_muted", "muted": req.muted, **st})
    return st


@app.get("/api/voice/mute")
def get_mic_mute_status() -> dict[str, Any]:
    """Retorna o estado atual de mute do microfone e voz."""
    from core import voice_daemon
    return {"muted": voice_daemon.is_muted()}


@app.get("/api/audio/last")
def get_last_audio(
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> Any:
    """Compatibilidade legada: retorna resposta.mp3 mais recente."""
    audio_path = os.path.join(os.path.dirname(__file__), "resposta.mp3")
    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Accept-Ranges": "bytes",
            }
        )
    raise HTTPException(status_code=404, detail="Nenhum áudio disponível.")


@app.get("/api/audio/{request_id}")
def get_audio_by_id(
    request_id: str,
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> Any:
    """Serve áudio gerado para um request_id específico — sem colisão entre usuários concorrentes."""
    safe = request_id.replace("-", "").replace("_", "")
    if not safe.isalnum() or len(request_id) > 64:
        raise HTTPException(status_code=400, detail="request_id inválido.")
    audio_cache_dir = os.path.join(os.path.dirname(__file__), "audio_cache")
    candidate = os.path.join(audio_cache_dir, f"{request_id}.mp3")
    if not os.path.exists(candidate) or os.path.getsize(candidate) == 0:
        candidate = os.path.join(os.path.dirname(__file__), "resposta.mp3")
    if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
        return FileResponse(
            candidate,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Accept-Ranges": "bytes",
            },
        )
    raise HTTPException(status_code=404, detail="Áudio não encontrado.")


def _capturar_frame_jpeg(largura_max: int = 1280, qualidade: int = 60) -> bytes | None:
    """Captura a tela do usuário e retorna um frame JPEG reduzido (ou None se indisponível)."""
    try:
        import io
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=False)
        if img.width > largura_max:
            nova_altura = int(img.height * largura_max / img.width)
            img = img.resize((largura_max, nova_altura))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=qualidade)
        return buf.getvalue()
    except Exception:
        return None


@app.get("/api/screen/status")
def screen_status() -> dict[str, Any]:
    """Indica se o servidor tem acesso à área de trabalho visível do usuário."""
    ok = _capturar_frame_jpeg(largura_max=64) is not None
    return {
        "screen_available": ok,
        "detail": None if ok else (
            "Servidor sem acesso à tela. Inicie a FRYIVS com iniciar_fryivs.bat "
            "(duplo clique) para que navegador, Word e Excel apareçam na sua tela."
        ),
    }


@app.get("/api/screen/stream")
async def screen_stream(
    fps: int = Query(default=5, ge=1, le=15),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> Any:
    """Stream MJPEG da tela em tempo real (use em <img src=...>)."""
    from fastapi.responses import StreamingResponse

    async def gerar():
        intervalo = 1.0 / fps
        loop = asyncio.get_event_loop()
        while True:
            frame = await loop.run_in_executor(None, _capturar_frame_jpeg)
            if frame is None:
                await asyncio.sleep(1.0)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                   + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
            await asyncio.sleep(intervalo)

    return StreamingResponse(
        gerar(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/api/memory")
def get_memories(
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Retorna o histórico de memórias gravadas no ChromaDB."""
    return {"memories": listar_memorias()}


@app.delete("/api/memory/{memory_id}")
def remove_memory(
    memory_id: str,
    _auth: None = Depends(_verificar_token),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, bool]:
    """Remove uma memória específica pelo id."""
    ok = deletar_memoria(memory_id)
    return {"success": ok}


@app.get("/api/skills")
def list_skills() -> dict[str, Any]:
    """Retorna todas as skills e seus respectivos esquemas."""
    return {
        "skills": list(SKILLS_REGISTRY.keys()),
        "schemas": ALL_SKILL_SCHEMAS
    }


@app.get("/api/skills/search")
def search_skills_endpoint(
    q: str = Query(..., min_length=1, description="Texto de consulta para busca semântica"),
    threshold: float = Query(default=0.80, ge=0.0, le=1.0, description="Limiar de similaridade cosseno (0=relaxado, 1=estrito)")
) -> dict[str, Any]:
    """Busca semântica vetorial de skills usando ChromaDB."""
    router = get_skill_router()
    matched = router.search_relevant_skills(q, top_k=5, threshold=threshold)
    matched_names = [m.get("function", {}).get("name") for m in matched]
    return {
        "query": q,
        "matched_count": len(matched),
        "matched_skills": matched_names,
        "schemas": matched
    }


@app.post("/api/commands/cancel")
async def cancel_commands(
    command_id: str | None = None,
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    from core.command_queue import get_queue
    from core.audio_player import parar
    queue = get_queue()
    stop_audio = queue.active_id is not None and (command_id is None or command_id == queue.active_id)
    cancelled = queue.cancel(command_id)
    if stop_audio:
        parar()
    return {"cancelled": cancelled}


@app.post("/api/skills/execute")
async def direct_execute_skill(
    req: SkillExecuteRequest,
    _auth: None = Depends(_verificar_token),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Executa diretamente uma skill pelo nome e argumentos."""
    from core.command_queue import get_queue
    resultado = await get_queue().run(lambda: asyncio.to_thread(execute_skill, req.skill, req.arguments))
    return {"skill": req.skill, "result": resultado}


@app.get("/api/knowledge/status")
def knowledge_status() -> dict[str, Any]:
    """Retorna o estado da base de conhecimento indexada no ChromaDB."""
    return kb_status()


@app.get("/api/knowledge/documents")
def knowledge_documents(
    limit: int = Query(default=40, ge=1, le=200),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Lista os documentos disponíveis na Base de Conhecimento da F.R.Y.I.Vs."""
    return {
        "status": kb_status(),
        "documents": listar_documentos_conhecimento(limit=limit),
    }


@app.post("/api/knowledge/reindex")
async def knowledge_reindex(
    reset: bool = False,
    _auth: None = Depends(_verificar_token),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Re-indexa a base de conhecimento. Use reset=true para recriar do zero."""
    loop = asyncio.get_event_loop()
    novos = await loop.run_in_executor(None, lambda: kb_indexar(forcar=reset, verbose=True))
    info = kb_status()
    return {
        "success": True,
        "novos_chunks": novos,
        "total_chunks": info.get("count", 0),
        "arquivos": info.get("arquivos_disponiveis", 0),
    }


@app.get("/api/knowledge/search")
async def knowledge_search(
    q: str = Query(..., min_length=1, description="Texto para buscar na base de conhecimento"),
    habilidade: str | None = Query(None, description="Filtrar por habilidade (ex: excel_avancado)"),
    k: int = Query(3, ge=1, le=10),
    _e2ee: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Busca trechos relevantes na base de conhecimento."""
    loop = asyncio.get_event_loop()
    resultado = await loop.run_in_executor(
        None, lambda: buscar_conhecimento(q, habilidade=habilidade, k=k)
    )
    return {"query": q, "resultado": resultado, "encontrou": bool(resultado)}


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
    e2ee_token: str = Query(default=""),
) -> None:
    """Canal WebSocket para eventos e comunicação em tempo real.

    Exige:
    - FRYIVS_API_TOKEN via query param `token` quando configurado (timing-safe com hmac.compare_digest)
    - Sessão E2EE desbloqueada e token válido via `e2ee_token` ou header `X-E2EE-Session`
      quando E2EE estiver ativo (fecha com código 4423 se bloqueado).
    """
    if _API_TOKEN:
        if not hmac.compare_digest(token.encode("utf-8"), _API_TOKEN.encode("utf-8")):
            await websocket.close(code=4401)
            return

    ws_e2ee = extract_e2ee_token(
        websocket.headers.get("x-e2ee-session", ""),
        websocket.headers.get("authorization", ""),
        e2ee_token,
    )
    if is_e2ee_required():
        if not is_session_unlocked() or validate_session_token(ws_e2ee) is None:
            await websocket.close(code=4423, reason="F.R.Y.I.Vs bloqueada (E2EE)")
            return

    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "welcome",
            "message": "Conectado ao núcleo neural da F.R.Y.I.Vs",
            "model": MODEL
        })
        while True:
            data = await websocket.receive_json()
            if is_e2ee_required():
                if not is_session_unlocked() or validate_session_token(ws_e2ee) is None:
                    await websocket.close(code=4423, reason="F.R.Y.I.Vs bloqueada (E2EE)")
                    return
            event_type = data.get("type")
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif event_type == "chat":
                msg = data.get("message", "")
                await websocket.send_json({"type": "state_change", "state": "thinking"})
                from core.assistant_pipeline import processar_comando
                result = await processar_comando(
                    texto=msg, origem="websocket", generate_speech=False,
                    tocar_local=False, broadcast_fn=manager.broadcast,
                )
                await websocket.send_json({"type": "chat_response", **result})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    print("Iniciando F.R.Y.I.Vs Server em http://127.0.0.1:8000...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
