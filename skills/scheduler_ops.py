"""
Módulo de Agendamento e Notificações Externas para F.R.Y.I.Vs.
Utiliza a biblioteca schedule para agendamento temporal de rotinas
e requests para envio de notificações e alertas em webhooks externos (WhatsApp, Telegram, etc).
"""

from __future__ import annotations

import json as _json
import os
import re as _re
import threading
import time
from pathlib import Path as _Path
from typing import Any, Final, Literal
from pydantic import BaseModel, Field

try:
    import schedule
except ImportError:
    schedule = None

try:
    import requests
except ImportError:
    requests = None


# ── Thread Daemon de Agendamento ────────────────────────────────────────────

_scheduler_running = False
_scheduler_lock = threading.Lock()
_jobs_registry: list[dict[str, Any]] = []


def _scheduler_loop() -> None:
    """Loop contínuo em background para disparar tarefas agendadas."""
    while True:
        if schedule is not None:
            try:
                schedule.run_pending()
            except Exception as e:
                print(f"[Scheduler] Erro ao executar tarefa agendada: {e}")
        time.sleep(1)


# ── Persistência ─────────────────────────────────────────────────────────

_JOBS_FILE = _Path(__file__).parent.parent / "data" / "scheduled_jobs.json"


def _salvar_jobs() -> None:
    """Persiste _jobs_registry em disco (metadados apenas, sem funções Python)."""
    try:
        _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _JOBS_FILE.write_text(
            _json.dumps(_jobs_registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[Scheduler] Aviso: não foi possível salvar jobs em disco: {e}")


def _carregar_jobs() -> None:
    """Carrega _jobs_registry do disco na inicialização do scheduler."""
    global _jobs_registry
    if not _JOBS_FILE.exists():
        return
    try:
        dados = _json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
        if isinstance(dados, list):
            _jobs_registry = dados
            print(f"[Scheduler] {len(dados)} job(s) restaurado(s) do disco.")
    except Exception as e:
        print(f"[Scheduler] Aviso: erro ao carregar jobs do disco: {e}")


def _garantir_scheduler_ativo() -> None:
    """Garante que a thread daemon do schedule esteja rodando e restaura jobs persistidos."""
    global _scheduler_running
    with _scheduler_lock:
        if not _scheduler_running:
            _carregar_jobs()
            t = threading.Thread(target=_scheduler_loop, daemon=True, name="FRYIVsSchedulerThread")
            t.start()
            _scheduler_running = True


# ── Schemas Pydantic ────────────────────────────────────────────────────────

class AgendarExecucaoParams(BaseModel):
    horario: str = Field(
        ...,
        description="Horário no formato 'HH:MM' (ex: '08:00', '14:30') ou minutos (ex: '15m')"
    )
    comando: str = Field(
        ...,
        description="Descrição da tarefa ou comando a ser executado"
    )
    tipo: Literal["diario", "intervalo_minutos"] = Field(
        default="diario",
        description="Tipo de repetição: 'diario' (todo dia no horário) ou 'intervalo_minutos'"
    )


class EnviarAlertaWebhookParams(BaseModel):
    mensagem: str = Field(..., description="Texto da notificação ou alerta a enviar")
    webhook_url: str | None = Field(
        default=None,
        description="URL do webhook (Telegram, Discord, WhatsApp Gateway). Se omitido, consulta variável de ambiente."
    )
    servico: str = Field(
        default="webhook",
        description="Nome amigável do canal de destino (ex: 'WhatsApp', 'Telegram')"
    )


# ── Funções Executáveis ─────────────────────────────────────────────────────

def agendar_execucao(horario: str, comando: str, tipo: str = "diario") -> str:
    """
    Agenda a execução periódica de uma rotina ou alerta no robô com a biblioteca schedule.
    """
    if schedule is None:
        return "Erro: A biblioteca schedule não está instalada no ambiente."

    _garantir_scheduler_ativo()

    try:
        h = horario.strip()
        cmd = comando.strip()

        def _tarefa() -> None:
            print(f"[Scheduler] Disparando tarefa agendada: {cmd}")
            try:
                # Encaminha pelo pipeline autorizado (mesma rota do chat HTTP)
                from core import assistant_pipeline as _pl
                import asyncio as _asyncio
                from core import voice_daemon as _vd
                loop = getattr(_vd, '_event_loop', None)
                if loop is not None and not loop.is_closed():
                    _asyncio.run_coroutine_threadsafe(
                        _pl.processar_comando(
                            texto=cmd,
                            origem="scheduler",
                            generate_speech=True,
                            tocar_local=True,
                        ),
                        loop,
                    )
                else:
                    # Fallback: falar o lembrete sem executar ferramenta
                    from core.tts import falar as _falar
                    _falar(f"Lembrete: {cmd}")
            except Exception as _exc_t:
                print(f"[Scheduler] Erro ao executar '{cmd}': {_exc_t}")

        job_info = {
            "horario": h,
            "comando": cmd,
            "tipo": tipo,
            "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        if tipo == "intervalo_minutos" or _re.search(r'\d+\s*m', h):
            m = _re.search(r'\d+', h)
            if not m:
                return f"Formato de intervalo inválido: '{h}'. Use '15m' ou '30min'."
            minutos = int(m.group())
            if minutos <= 0:
                return "Intervalo deve ser maior que zero."
            schedule.every(minutos).minutes.do(_tarefa)
            _jobs_registry.append(job_info)
            _salvar_jobs()
            return f"Rotina agendada: executar '{cmd}' a cada {minutos} minutos."

        # Agendamento diário em horário fixo HH:MM
        schedule.every().day.at(h).do(_tarefa)
        _jobs_registry.append(job_info)
        _salvar_jobs()
        return f"Rotina agendada: executar '{cmd}' todos os dias às {h}."
    except Exception as e:
        return f"Falha ao agendar tarefa: {e}"


def listar_agendamentos() -> str:
    """Lista todas as tarefas agendadas na F.R.Y.I.Vs."""
    if not _jobs_registry:
        return "Não há rotinas agendadas no momento."
    itens = [f"{j['comando']} ({j['horario']} - {j['tipo']})" for j in _jobs_registry]
    return f"Tarefas agendadas ativas: {'; '.join(itens)}."


def enviar_alerta_webhook(
    mensagem: str,
    webhook_url: str | None = None,
    servico: str = "webhook"
) -> str:
    """
    Envia uma notificação externa via requests para WhatsApp, Telegram ou Discord.
    """
    if requests is None:
        return "Erro: A biblioteca requests não está disponível."

    url = webhook_url or os.environ.get("WEBHOOK_URL") or os.environ.get("TELEGRAM_WEBHOOK_URL")
    if not url:
        return (
            f"Alerta preparado ('{mensagem[:60]}...'), porém nenhuma URL de webhook foi configurada. "
            "Defina 'WEBHOOK_URL' no arquivo .env ou forneça o parâmetro 'webhook_url'."
        )

    try:
        # Detecta tipo de webhook pela URL e formata payload correto
        url_lower = url.lower()
        if "discord.com/api/webhooks" in url_lower:
            payload = {"content": mensagem, "username": "F.R.Y.I.Vs"}
        elif "api.telegram.org" in url_lower:
            payload = {"text": f"[F.R.Y.I.Vs] {mensagem}"}
        elif "hooks.slack.com" in url_lower:
            payload = {"text": f"*F.R.Y.I.Vs*: {mensagem}"}
        else:
            payload = {
                "origem": "F.R.Y.I.Vs AI Assistant",
                "servico": servico,
                "mensagem": mensagem,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code in (200, 201, 204):
            return f"Notificação externa enviada com sucesso para {servico} (Status {res.status_code})."
        return f"Envio concluído com resposta {res.status_code}: {res.text[:100]}"
    except Exception as e:
        return f"Falha ao enviar notificação externa via webhook: {e}"


# ── Schemas OpenAPI ─────────────────────────────────────────────────────────

SCHEDULER_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "agendar_execucao",
            "description": "Agenda horários para o robô executar tarefas ou lembretes (ex: todo dia às 08:00 ou a cada 15 minutos).",
            "parameters": {
                "type": "object",
                "properties": {
                    "horario": {
                        "type": "string",
                        "description": "Horário no formato 'HH:MM' (ex: '08:00') ou minutos (ex: '15m')"
                    },
                    "comando": {
                        "type": "string",
                        "description": "Nome ou descrição do que deve ser executado no horário"
                    },
                    "tipo": {
                        "type": "string",
                        "enum": ["diario", "intervalo_minutos"],
                        "description": "Tipo de repetição ('diario' ou 'intervalo_minutos')"
                    }
                },
                "required": ["horario", "comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_agendamentos",
            "description": "Lista todas as tarefas agendadas e ativas na assistente.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_alerta_webhook",
            "description": "Envia notificações ou alertas externos para WhatsApp, Telegram ou Discord via webhook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mensagem": {
                        "type": "string",
                        "description": "Mensagem ou alerta a ser enviado"
                    },
                    "webhook_url": {
                        "type": "string",
                        "description": "URL do webhook de destino (opcional se configurado no .env)"
                    },
                    "servico": {
                        "type": "string",
                        "description": "Nome do canal (ex: 'WhatsApp', 'Telegram', 'Discord')"
                    }
                },
                "required": ["mensagem"]
            }
        }
    }
]
