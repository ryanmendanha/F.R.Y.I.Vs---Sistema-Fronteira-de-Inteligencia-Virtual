"""
Skills Pydantic de Delegação e Governança Multi-Agente (Hermes Agent WSL2) da F.R.Y.I.Vs.

Expõe 4 ferramentas tipadas para o roteador/LLM:
- `delegar_missao_hermes`: despacha missão assíncrona em background para um perfil especialista.
- `consultar_status_agentes`: consulta progresso, orçamento diário e aprovações Tier 3 pendentes.
- `cancelar_missao_agente`: cancela uma missão específica ou aciona o Kill-Switch global.
- `listar_perfis_hermes`: lista os 4 perfis especialistas Hermes disponíveis e seus sandboxes.
"""

from __future__ import annotations

from typing import Any, Callable, Final, Literal

from pydantic import BaseModel, Field, ValidationError

from core.agent_orchestrator import (
    BudgetGuardError,
    HERMES_PROFILES,
    HermesProfileName,
    get_orchestrator,
)


class DelegarMissaoHermesParams(BaseModel):
    perfil: HermesProfileName = Field(
        ...,
        description="Perfil especialista: 'pesquisador', 'organizador', 'ideias' ou 'engenheiro'.",
    )
    missao: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Descrição clara da missão assíncrona a delegar ao subagente.",
    )
    contexto: str = Field(
        default="",
        max_length=32000,
        description="Contexto ou dados complementares opcionais para o subagente.",
    )
    contexto_externo: bool = Field(
        default=False,
        description="Marque True quando o contexto incluir conteúdo externo web/RAG não confiável (ativa Taint-Tracking).",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=256,
        description="Chave opcional de idempotência para evitar duplicação em janela de 15 minutos.",
    )


class ConsultarStatusAgentesParams(BaseModel):
    job_id: str | None = Field(
        default=None,
        description="ID opcional de uma missão específica. Se omitido, retorna resumo geral.",
    )


class CancelarMissaoAgenteParams(BaseModel):
    job_id: str | None = Field(
        default=None,
        description="ID da missão a cancelar (ou 'all' para cancelar todas).",
    )
    cancelar_todos: bool = Field(
        default=False,
        description="Se True, aciona o Kill-Switch de emergência encerrando todos os agentes ativos.",
    )


class ListarPerfisHermesParams(BaseModel):
    pass


def delegar_missao_hermes(
    perfil: Literal["pesquisador", "organizador", "ideias", "engenheiro"],
    missao: str,
    contexto: str = "",
    contexto_externo: bool = False,
    idempotency_key: str | None = None,
) -> str:
    """Delega uma missão assíncrona em background para um dos 4 perfis especialistas do Hermes Agent."""
    try:
        params = DelegarMissaoHermesParams(
            perfil=perfil,
            missao=missao,
            contexto=contexto,
            contexto_externo=contexto_externo,
            idempotency_key=idempotency_key,
        )
    except ValidationError as exc:
        return f"Parâmetros inválidos para delegar missão ao Hermes: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    try:
        job = orch.submit_job(
            profile=params.perfil,
            task=params.missao,
            context=params.contexto,
            context_tainted=params.contexto_externo,
            idempotency_key=params.idempotency_key,
            actor="fryivs_skill",
            dispatch_background=True,
        )
    except BudgetGuardError as exc:
        return f"Senhor, o Budget Guard bloqueou a delegação ao Hermes: {exc}"
    except ValueError as exc:
        return f"Não foi possível delegar a missão ao Hermes: {exc}"

    if job.deduplicated:
        return (
            f"Senhor, uma missão idêntica já foi registrada recentemente (idempotência ativa). "
            f"Job existente: {job.job_id} (perfil '{job.profile}', status: {job.status})."
        )

    if job.status == "awaiting_approval":
        return (
            f"Senhor, por conter contexto externo não confiável (Taint-Tracking), a missão "
            f"{job.job_id} para o perfil '{job.profile}' aguarda sua aprovação explícita Tier 3 "
            f"(aprovação ID: {job.approval_id})."
        )

    return (
        f"Protocolo assíncrono iniciado em segundo plano, senhor. "
        f"Missão {job.job_id} delegada ao perfil Hermes '{job.profile}' "
        f"(status: {job.status}, limite de {job.max_steps} passos)."
    )


def consultar_status_agentes(job_id: str | None = None) -> str:
    """Consulta o status de uma missão específica ou o panorama geral dos agentes e orçamento."""
    try:
        params = ConsultarStatusAgentesParams(job_id=job_id)
    except ValidationError as exc:
        return f"Parâmetros inválidos ao consultar status dos agentes: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    if params.job_id:
        job = orch.get_job(params.job_id.strip())
        if job is None:
            return f"Senhor, não encontrei nenhuma missão registrada com o ID '{params.job_id}'."
        extra = ""
        if job.result:
            extra = f" Resultado: {job.result[:240]}"
        elif job.error:
            extra = f" Aviso/Erro: {job.error[:240]}"
        return (
            f"Missão {job.job_id} (perfil '{job.profile}'): status={job.status}, "
            f"progresso={job.progress_pct}%, passos={job.steps_completed}/{job.max_steps}, "
            f"tempo={job.elapsed_seconds():.1f}s, tokens={job.tokens_used}.{extra}"
        )

    snapshot = orch.get_status()
    budget = snapshot["budget"]
    active = snapshot["active_jobs"]
    pending_approvals = snapshot["pending_approvals"]
    hermes_state = snapshot["hermes"]["state"]

    resumo_jobs = (
        "; ".join(f"{j['profile']}:{j['status']}({j['job_id'][:8]})" for j in active[:4])
        if active
        else "nenhuma missão ativa"
    )
    return (
        f"Senhor, Hermes Gateway está '{hermes_state}'. "
        f"Concorrência: {budget['active_concurrent']}/{budget['max_concurrent_agents']} agentes ativos "
        f"({resumo_jobs}). Orçamento diário: US$ {budget['daily_usd_used']:.4f} / "
        f"US$ {budget['max_usd_per_day']:.2f} ({budget['daily_tokens_used']} tokens). "
        f"Aprovações Tier 3 pendentes: {len(pending_approvals)}."
    )


def cancelar_missao_agente(
    job_id: str | None = None,
    cancelar_todos: bool = False,
) -> str:
    """Cancela uma missão específica ou aciona o Kill-Switch global de agentes."""
    try:
        params = CancelarMissaoAgenteParams(job_id=job_id, cancelar_todos=cancelar_todos)
    except ValidationError as exc:
        return f"Parâmetros inválidos ao cancelar missão: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    if params.cancelar_todos or (params.job_id and params.job_id.strip().lower() in ("all", "todos")):
        res = orch.kill_all_jobs(actor="fryivs_skill", reason="kill_switch_voice_or_skill")
        return (
            f"Kill-Switch acionado, senhor. {res['killed_count']} missão(ões) encerrada(s) "
            f"imediatamente e todos os slots de concorrência liberados."
        )

    if not params.job_id or not params.job_id.strip():
        return (
            "Senhor, informe o 'job_id' da missão que deseja cancelar ou defina "
            "'cancelar_todos=True' para encerrar todos os agentes ativos."
        )

    job = orch.cancel_job(params.job_id.strip(), actor="fryivs_skill", reason="cancelled_by_skill")
    if job is None:
        return f"Senhor, não localizei nenhuma missão com ID '{params.job_id}'."
    return f"Missão {job.job_id} (perfil '{job.profile}') cancelada com sucesso, senhor."


def listar_perfis_hermes() -> str:
    """Lista os 4 perfis especialistas Hermes configurados e seus níveis de isolamento."""
    ListarPerfisHermesParams()
    linhas = [
        f"- {cfg['name']} ({cfg['label']}): {cfg['mission']} [Sandbox: {cfg['sandbox']}]"
        for cfg in HERMES_PROFILES.values()
    ]
    return "Perfis especialistas Hermes Agent disponíveis:\n" + "\n".join(linhas)


HERMES_SKILLS_REGISTRY: Final[dict[str, Callable[..., str]]] = {
    "delegar_missao_hermes": delegar_missao_hermes,
    "consultar_status_agentes": consultar_status_agentes,
    "cancelar_missao_agente": cancelar_missao_agente,
    "listar_perfis_hermes": listar_perfis_hermes,
}


HERMES_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "delegar_missao_hermes",
            "description": (
                "Delega uma missão longa ou especializada em segundo plano para um subagente "
                "Hermes Agent (WSL2) sem bloquear o atendimento por voz/chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "perfil": {
                        "type": "string",
                        "enum": ["pesquisador", "organizador", "ideias", "engenheiro"],
                        "description": "Perfil especialista que executará a missão.",
                    },
                    "missao": {
                        "type": "string",
                        "description": "Objetivo completo e instruções da missão assíncrona.",
                    },
                    "contexto": {
                        "type": "string",
                        "description": "Contexto adicional opcional para subsidiar o subagente.",
                    },
                    "contexto_externo": {
                        "type": "boolean",
                        "description": (
                            "True se o contexto vier de páginas web ou RAG externo não confiável "
                            "(exigirá aprovação Human-in-the-Loop via Taint-Tracking)."
                        ),
                    },
                    "idempotency_key": {
                        "type": "string",
                        "description": "Chave opcional de deduplicação para evitar execuções repetidas em 15 minutos.",
                    },
                },
                "required": ["perfil", "missao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_status_agentes",
            "description": (
                "Consulta o status das missões delegadas aos subagentes Hermes, consumo do "
                "Budget Guard (tokens/USD, concorrência) e aprovações Tier 3 pendentes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "ID opcional de uma missão específica para detalhes completos.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancelar_missao_agente",
            "description": (
                "Cancela uma missão específica do Hermes Agent ou aciona o Kill-Switch de emergência "
                "para encerrar imediatamente todos os agentes ativos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "ID da missão a cancelar (ou 'all' para encerrar todas).",
                    },
                    "cancelar_todos": {
                        "type": "boolean",
                        "description": "True para acionar o Kill-Switch global encerrando todos os agentes ativos.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_perfis_hermes",
            "description": (
                "Lista os 4 perfis especialistas do Hermes Agent (pesquisador, engenheiro, "
                "analista e sentinela), suas ferramentas liberadas e isolamento de sandbox."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]
