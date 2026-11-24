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
from typing import Any, Callable, Final, Literal
from pydantic import BaseModel, Field

try:
    import schedule
except ImportError:
    schedule = None

try:
    import requests
except ImportError:
    requests = None


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


def _job_tag(job_info: dict[str, Any]) -> str:
    """Chave determinística para evitar registros duplicados no objeto `schedule`."""
    h = str(job_info.get("horario", "")).strip()
    cmd = str(job_info.get("comando", "")).strip()
    tipo = str(job_info.get("tipo", "diario")).strip()
    return f"fryivs_job:{tipo}|{h}|{cmd}"


def _criar_callback_tarefa(cmd: str) -> Callable[[], None]:
    """Cria closure isolada por tarefa agendada (evita captura mutável em loops)."""
    def _tarefa() -> None:
        print(f"[Scheduler] Disparando tarefa agendada: {cmd}")
        try:
            from core import assistant_pipeline as _pl
            import asyncio as _asyncio
            from core import voice_daemon as _vd
            loop = getattr(_vd, "_event_loop", None)
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
                from core.tts import falar as _falar
                _falar(f"Lembrete: {cmd}")
        except Exception as _exc_t:
            print(f"[Scheduler] Erro ao executar '{cmd}': {_exc_t}")

    return _tarefa


def _registrar_job_no_schedule(job_info: dict[str, Any]) -> tuple[bool, str]:
    """
    Registra concretamente um `job_info` no objeto `schedule`, prevenindo duplicatas via tag.

    Retorna:
        `(registrado, detalhe)` onde `detalhe` descreve a periodicidade, `'already_registered'`
        ou motivo do erro.
    """
    if schedule is None:
        return False, "schedule_unavailable"

    h = str(job_info.get("horario", "")).strip()
    cmd = str(job_info.get("comando", "")).strip()
    tipo = str(job_info.get("tipo", "diario")).strip()
    if not h or not cmd:
        return False, "invalid_job_info"

    tag = _job_tag(job_info)
    for existing in getattr(schedule, "jobs", []):
        if tag in getattr(existing, "tags", set()):
            return False, "already_registered"

    tarefa = _criar_callback_tarefa(cmd)

    if tipo == "intervalo_minutos" or _re.search(r"\d+\s*m", h):
        m = _re.search(r"\d+", h)
        if not m:
            return False, f"Formato de intervalo inválido: '{h}'. Use '15m' ou '30min'."
        minutos = int(m.group())
        if minutos <= 0:
            return False, "Intervalo deve ser maior que zero."
        schedule.every(minutos).minutes.do(tarefa).tag(tag)
        return True, f"a cada {minutos} minutos"

    schedule.every().day.at(h).do(tarefa).tag(tag)
    return True, f"todos os dias às {h}"


def _carregar_jobs() -> None:
    """
    Carrega `_jobs_registry` do disco na inicialização do scheduler e RE-AGENDA
    cada rotina no objeto `schedule` (corrigindo o bug do Agendador Zumbi).
    """
    global _jobs_registry
    if not _JOBS_FILE.exists():
        return
    try:
        dados = _json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
        if isinstance(dados, list):
            deduped: list[dict[str, Any]] = []
            seen_tags: set[str] = set()
            reagendados = 0
            for item in dados:
                if not isinstance(item, dict):
                    continue
                tag = _job_tag(item)
                if tag in seen_tags:
                    continue
                seen_tags.add(tag)
                deduped.append(item)
                try:
                    ok, _det = _registrar_job_no_schedule(item)
                    if ok:
                        reagendados += 1
                except Exception as exc_reg:
                    print(f"[Scheduler] Aviso: falha ao reagendar job '{item.get('comando')}': {exc_reg}")
            _jobs_registry = deduped
            print(
                f"[Scheduler] {len(deduped)} job(s) restaurado(s) do disco "
                f"({reagendados} reagendado(s) no schedule)."
            )
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

        job_info = {
            "horario": h,
            "comando": cmd,
            "tipo": tipo,
            "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        registrado, detalhe = _registrar_job_no_schedule(job_info)
        if not registrado:
            if detalhe == "already_registered":
                tag = _job_tag(job_info)
                if not any(_job_tag(j) == tag for j in _jobs_registry):
                    _jobs_registry.append(job_info)
                    _salvar_jobs()
                return f"Rotina já agendada: '{cmd}' ({h})."
            return detalhe

        tag = _job_tag(job_info)
        if not any(_job_tag(j) == tag for j in _jobs_registry):
            _jobs_registry.append(job_info)
        _salvar_jobs()
        return f"Rotina agendada: executar '{cmd}' {detalhe}."
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
    servico: str = "webhook",
    hmac_secret: str | None = None,
) -> str:
    """
    Envia uma notificação externa via requests para WhatsApp, Telegram, Discord ou n8n,
    com proteção contra SSRF (`validar_url_externa`) e assinatura HMAC-SHA256 opcional.
    """
    if requests is None:
        return "Erro: A biblioteca requests não está disponível."

    url = webhook_url or os.environ.get("WEBHOOK_URL") or os.environ.get("TELEGRAM_WEBHOOK_URL")
    if not url:
        return (
            f"Alerta preparado ('{mensagem[:60]}...'), porém nenhuma URL de webhook foi configurada. "
            "Defina 'WEBHOOK_URL' no arquivo .env ou forneça o parâmetro 'webhook_url'."
        )

    from core.n8n_bridge import sign_webhook_payload, validar_url_externa

    ok_url, motivo_ssrf = validar_url_externa(
        url,
        resolve_dns=not bool(os.environ.get("PYTEST_CURRENT_TEST")),
    )
    if not ok_url:
        return f"Envio bloqueado por proteção SSRF: {motivo_ssrf}"

    try:
        url_lower = url.lower()
        if "discord.com/api/webhooks" in url_lower:
            payload: dict[str, Any] = {"content": mensagem, "username": "F.R.Y.I.Vs"}
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

        raw_body = _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        effective_secret = (
            hmac_secret
            if hmac_secret is not None
            else (os.environ.get("N8N_HMAC_SECRET") or os.environ.get("WEBHOOK_HMAC_SECRET") or "")
        ).strip()

        if effective_secret:
            headers = sign_webhook_payload(raw_body, effective_secret)
        else:
            headers = {"Content-Type": "application/json"}

        res = requests.post(
            url,
            data=raw_body.encode("utf-8"),
            headers=headers,
            timeout=5,
            allow_redirects=False,
        )
        if res.status_code in (200, 201, 204):
            selo = " [HMAC-SHA256]" if effective_secret else ""
            return f"Notificação externa enviada com sucesso para {servico}{selo} (Status {res.status_code})."
        return f"Envio concluído com resposta {res.status_code}: {res.text[:100]}"
    except Exception as e:
        return f"Falha ao enviar notificação externa via webhook: {e}"


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
