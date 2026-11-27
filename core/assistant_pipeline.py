"""
Pipeline unificado de processamento de comandos (Voz, Daemon e Chat Web) da F.R.Y.I.Vs.

Centraliza:
1. Busca paralela de memória semântica + base de conhecimento + artefato ativo da sessão.
2. Inferência com histórico conversacional unificado (`core.session_state`).
3. Persistência em memória vetorial (ChromaDB) e no histórico da sessão.
4. Síntese de voz (TTS) e reprodução local nas caixas de som (`core.audio_player`).
5. Notificação em tempo real via WebSocket e barra flutuante FRY.png (`core.overlay`).
"""

from __future__ import annotations

import asyncio
import os
import uuid
import functools
import logging
from core.command_control import Command, CommandCancelled, check_cancelled
from core.command_queue import get_queue
from typing import Any, Awaitable, Callable

from core.audio_player import tocar as tocar_audio_local
from core.knowledge_base import buscar_conhecimento
from core.respostas_cache import buscar_resposta_cache
from core.llm import DEFAULT_PROFILE, ask_fryvis, _is_direct_time_date_query
from core.memory import buscar_contexto, salvar_memoria
from core.overlay import status_overlay
from core.session_state import (
    contexto_para_llm,
    mesclar_historico,
    registrar_turno,
)
from core.tts import AUDIO_CACHE_DIR, falar, falar_streaming_local
from core.runtime_mode import is_web_mode


def _deve_tocar_local(origem: str, explicito: bool | None) -> bool:
    if explicito is not None:
        return explicito
    env_flag = os.getenv("VOICE_LOCAL_PLAYBACK", "true").strip().lower()
    if env_flag in ("false", "0", "no", "nao", "não"):
        return False
    return origem in ("voz", "daemon")


def _serialized(function):
    @functools.wraps(function)
    async def wrapped(*args, **kwargs):
        from core.e2ee_auth import is_session_unlocked
        if not is_session_unlocked():
            return {
                "locked": True,
                "user_message": kwargs.get("texto", args[0] if args else ""),
                "transcription": "",
                "response": "F.R.Y.I.Vs bloqueada (E2EE). Desbloqueie com senha antes de interagir.",
                "context_used": "",
                "tools_executed": [],
                "has_audio": False,
                "audio_url": "",
                "played_locally": False,
                "from_cache": False,
            }
        command = Command()
        broadcast = kwargs.get("broadcast_fn")
        from core.mute_state import iniciar_processamento, finalizar_processamento, definir_falando
        iniciar_processamento()
        async def operation():
            try:
                result = await function(*args, **kwargs)
                result["command_id"] = command.id
                return result
            finally:
                if broadcast:
                    try:
                        await broadcast({"type": "state_change", "state": "idle", "command_id": command.id})
                    except Exception:
                        logging.getLogger(__name__).exception("Falha ao publicar estado final")
        try:
            return await get_queue().run(operation, command)
        except CommandCancelled:
            return {
                "command_id": command.id, "cancelled": True,
                "user_message": kwargs.get("texto", args[0] if args else ""),
                "transcription": "", "response": "Comando cancelado.",
                "context_used": "", "tools_executed": [], "has_audio": False,
                "audio_url": "", "played_locally": False,
            }
        finally:
            finalizar_processamento()
            definir_falando(False, cooldown=0.8)
    return wrapped


@_serialized
async def processar_comando(
    texto: str,
    origem: str = "chat",
    profile: str = DEFAULT_PROFILE,
    provider: str | None = None,
    use_memory: bool = True,
    generate_speech: bool = True,
    history: list[dict[str, str]] | None = None,
    tocar_local: bool | None = None,
    broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    buscar_contexto_fn: Callable[..., str] = buscar_contexto,
    buscar_conhecimento_fn: Callable[..., str] = buscar_conhecimento,
    ask_fryvis_fn: Callable[..., tuple[str, list[dict[str, Any]]]] = ask_fryvis,
    salvar_memoria_fn: Callable[..., Any] = salvar_memoria,
    falar_fn: Callable[..., str] = falar,
    buscar_resposta_cache_fn: Callable[[str], dict[str, Any] | None] | None = buscar_resposta_cache,
) -> dict[str, Any]:
    """
    Executa todo o ciclo de inteligência para um comando de texto ou voz.
    """
    from core.e2ee_auth import is_session_unlocked
    if not is_session_unlocked():
        return {
            "locked": True,
            "user_message": texto,
            "transcription": "",
            "response": "F.R.Y.I.Vs bloqueada (E2EE). Desbloqueie com senha antes de interagir.",
            "context_used": "",
            "tools_executed": [],
            "has_audio": False,
            "audio_url": "",
            "played_locally": False,
            "from_cache": False,
        }

    if broadcast_fn:
        await broadcast_fn({
            "type": "state_change",
            "state": "thinking",
            "detail": "Consultando memória e analisando comandos...",
        })
    if origem in ("voz", "daemon"):
        status_overlay(f"Processando: {texto[:42]}", ativo=True, duracao=10.0)

    cache_hit = None
    if buscar_resposta_cache_fn:
        try:
            cache_hit = await asyncio.to_thread(lambda: buscar_resposta_cache_fn(texto))
        except Exception as e:
            print(f"[Pipeline] Erro ao consultar respostas_cache: {e}")

    eh_hora_data_direta = (ask_fryvis_fn is ask_fryvis) and _is_direct_time_date_query(texto)

    if cache_hit:
        resposta = cache_hit["resposta"]
        ferramentas_executadas = []
        contexto = f"[Cache Pré-indexado: {cache_hit.get('match_type', 'exato')} (score: {cache_hit.get('score', 1.0)})]"
    elif eh_hora_data_direta:
        contexto = ""
        resposta, ferramentas_executadas = await asyncio.to_thread(
            lambda: ask_fryvis_fn(
                prompt=texto,
                context="",
                conversation_history=[],
                enable_semantic_skill_routing=True,
                profile=profile,
                provider=provider,
            ),
        )
    else:
        async def _buscar_mem() -> str:
            if use_memory:
                try:
                    return await asyncio.to_thread(lambda: buscar_contexto_fn(texto, n_resultados=3))
                except Exception as e:
                    print(f"[Pipeline] Erro ao buscar memória: {e}")
            return ""

        async def _buscar_kb() -> str:
            try:
                return await asyncio.to_thread(lambda: buscar_conhecimento_fn(texto, k=2))
            except Exception as e:
                print(f"[Pipeline] Erro ao buscar base de conhecimento: {e}")
            return ""

        mem_ctx, kb_ctx = await asyncio.gather(_buscar_mem(), _buscar_kb())
        artefato_ctx = contexto_para_llm()
        partes_contexto = [p for p in [mem_ctx, kb_ctx, artefato_ctx] if p]
        contexto = "\n\n".join(partes_contexto)

        hist_efetivo = mesclar_historico(history)

        resposta, ferramentas_executadas = await asyncio.to_thread(
            lambda: ask_fryvis_fn(
                prompt=texto,
                context=contexto,
                conversation_history=hist_efetivo,
                enable_semantic_skill_routing=True,
                profile=profile,
                provider=provider,
            ),
        )

    check_cancelled()
    from core.stt import eh_alucinacao_whisper
    eh_aluc = eh_alucinacao_whisper(texto)
    if resposta and not eh_aluc:
        registrar_turno(texto, resposta)

    if use_memory and resposta and not eh_hora_data_direta and not cache_hit and not eh_aluc:
        mem_id = str(uuid.uuid4())
        registro = f"Usuário: {texto} | FRYVIS: {resposta}"
        await asyncio.to_thread(salvar_memoria_fn, registro, mem_id)

    has_audio = False
    audio_url = ""
    played_locally = False
    chat_response_enviado = False

    if generate_speech and resposta and is_session_unlocked():
        from core.mute_state import definir_falando
        definir_falando(True)
        if broadcast_fn:
            await broadcast_fn({
                "type": "state_change",
                "state": "speaking",
                "detail": "Sintetizando voz...",
            })
        deve_tocar = _deve_tocar_local(origem, tocar_local)
        usar_streaming_sentencas = (
            deve_tocar
            and falar_fn is falar
            and len(resposta) > 110
        )

        if usar_streaming_sentencas:
            if broadcast_fn and origem == "daemon":
                await broadcast_fn({
                    "type": "chat_response",
                    "user_message": texto,
                    "response": resposta,
                    "tools_executed": ferramentas_executadas,
                    "has_audio": True,
                    "audio_url": "",
                    "played_locally": True,
                })
                chat_response_enviado = True
            status_overlay("Respondendo ao senhor...", ativo=True, duracao=8.0)
            audio_path, played_locally = await asyncio.to_thread(
                lambda: falar_streaming_local(resposta, output_path="resposta.mp3")
            )
            check_cancelled()
            if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                has_audio = True
                audio_url = f"/api/audio/last?v={uuid.uuid4().hex[:8]}"
        else:
            if is_web_mode():
                from core.runtime_mode import get_audio_cache_dir
                req_audio_id = f"resp_{uuid.uuid4().hex[:16]}"
                cache_dir = str(get_audio_cache_dir())
                os.makedirs(cache_dir, exist_ok=True)
                target_out = os.path.join(cache_dir, f"{req_audio_id}.mp3")
                audio_path = await asyncio.to_thread(
                    lambda: falar_fn(resposta, output_path=target_out)
                )
                check_cancelled()
                if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                    has_audio = True
                    audio_url = f"/api/audio/{req_audio_id}"
            else:
                audio_path = await asyncio.to_thread(lambda: falar_fn(resposta, output_path="resposta.mp3"))
                check_cancelled()
                if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                    has_audio = True
                    audio_url = f"/api/audio/last?v={uuid.uuid4().hex[:8]}"
                    if broadcast_fn and origem == "daemon":
                        await broadcast_fn({
                            "type": "chat_response",
                            "user_message": texto,
                            "response": resposta,
                            "tools_executed": ferramentas_executadas,
                            "has_audio": has_audio,
                            "audio_url": audio_url,
                            "played_locally": bool(deve_tocar),
                        })
                        chat_response_enviado = True
                    if deve_tocar:
                        status_overlay("Respondendo ao senhor...", ativo=True, duracao=8.0)
                        played_locally = await asyncio.to_thread(
                            lambda: tocar_audio_local(audio_path, bloquear=True)
                        )
        definir_falando(False, cooldown=0.8)

    if broadcast_fn and origem == "daemon" and not chat_response_enviado:
        await broadcast_fn({
            "type": "chat_response",
            "user_message": texto,
            "response": resposta,
            "tools_executed": ferramentas_executadas,
            "has_audio": has_audio,
            "audio_url": audio_url,
            "played_locally": played_locally,
        })


    return {
        "user_message": texto,
        "transcription": texto,
        "response": resposta,
        "context_used": contexto,
        "tools_executed": ferramentas_executadas,
        "has_audio": has_audio,
        "audio_url": audio_url,
        "played_locally": played_locally,
        "from_cache": bool(cache_hit),
    }

