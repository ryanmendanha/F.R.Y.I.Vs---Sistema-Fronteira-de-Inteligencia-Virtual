"""
Skills Pydantic de Manipulação Multi-Agente e Controle do Escritório 3D da F.R.Y.I.Vs.

Expõe 6 ferramentas tipadas para a F.R.Y.I.Vs controlar seus 4 agentes por voz ou chat:
- `delegar_missao_hermes`: despacha missão em segundo plano para pesquisador, organizador, ideias ou engenheiro.
- `consultar_status_agentes`: consulta progresso, orçamento e lê resultados concluídos dos agentes.
- `curar_resultado_agente`: indexa na Base de Conhecimento ou descarta o resultado de um agente.
- `controlar_escritorio_agentes`: abre/fecha o Escritório 3D, foca em um agente ou comanda festa/atividades.
- `cancelar_missao_agente`: cancela a missão de um agente (por perfil ou ID) ou aciona Kill-Switch.
- `listar_perfis_hermes`: lista os 4 agentes especialistas disponíveis.
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

OfficeActionType = Literal["abrir", "fechar", "focar", "festa", "atividade", "fila"]
OfficeActivityType = Literal["coffee", "pingpong", "game", "band", "dance", "chat", "plant"]


class DelegarMissaoHermesParams(BaseModel):
    perfil: HermesProfileName = Field(
        ...,
        description="Agente especialista: 'pesquisador', 'organizador', 'ideias' ou 'engenheiro'.",
    )
    missao: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Descrição clara da missão assíncrona a delegar ao agente.",
    )
    contexto: str = Field(
        default="",
        max_length=32000,
        description="Contexto complementar opcional.",
    )
    contexto_externo: bool = Field(
        default=False,
        description="True quando o contexto incluir dados externos não confiáveis.",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=256,
    )
    abrir_escritorio: bool = Field(
        default=False,
        description="Se True, abre automaticamente o Escritório 3D na tela focando neste agente.",
    )


class ConsultarStatusAgentesParams(BaseModel):
    perfil: HermesProfileName | None = Field(
        default=None,
        description="Filtra pelo nome do agente ('pesquisador', 'organizador', 'ideias', 'engenheiro').",
    )
    job_id: str | None = Field(
        default=None,
        description="ID opcional de uma missão específica.",
    )


class CurarResultadoAgenteParams(BaseModel):
    acao: Literal["indexar", "descartar"] = Field(
        ...,
        description="'indexar' para salvar na Base de Conhecimento da IA ou 'descartar' para remover.",
    )
    perfil: HermesProfileName | None = Field(
        default=None,
        description="Agente cujo último resultado concluído deve ser indexado ou descartado.",
    )
    job_id: str | None = Field(
        default=None,
        description="ID opcional da missão (se omitido, usa a missão concluída mais recente).",
    )
    titulo: str | None = Field(
        default=None,
        max_length=160,
        description="Título opcional ao indexar na Base de Conhecimento.",
    )


class ControlarEscritorioAgentesParams(BaseModel):
    acao: OfficeActionType = Field(
        ...,
        description="Ação visual no Escritório 3D: 'abrir', 'fechar', 'focar', 'festa', 'atividade' ou 'fila'.",
    )
    perfil: HermesProfileName | None = Field(
        default=None,
        description="Agente alvo ao usar 'focar' ou 'atividade'.",
    )
    atividade: OfficeActivityType | None = Field(
        default=None,
        description="Atividade no escritório: 'coffee', 'pingpong', 'game', 'band', 'dance', 'chat' ou 'plant'.",
    )


class CancelarMissaoAgenteParams(BaseModel):
    perfil: HermesProfileName | None = Field(
        default=None,
        description="Nome do agente em execução a cancelar.",
    )
    job_id: str | None = Field(
        default=None,
        description="ID da missão a cancelar (ou 'all' para cancelar todas).",
    )
    cancelar_todos: bool = Field(
        default=False,
        description="Se True, aciona o Kill-Switch encerrando todos os agentes ativos.",
    )


class ListarPerfisHermesParams(BaseModel):
    pass


def delegar_missao_hermes(
    perfil: Literal["pesquisador", "organizador", "ideias", "engenheiro"],
    missao: str,
    contexto: str = "",
    contexto_externo: bool = False,
    idempotency_key: str | None = None,
    abrir_escritorio: bool = False,
) -> str:
    """Delega uma missão em segundo plano para um dos 4 agentes especialistas da F.R.Y.I.Vs."""
    try:
        params = DelegarMissaoHermesParams(
            perfil=perfil,
            missao=missao,
            contexto=contexto,
            contexto_externo=contexto_externo,
            idempotency_key=idempotency_key,
            abrir_escritorio=abrir_escritorio,
        )
    except ValidationError as exc:
        return f"Parâmetros inválidos para delegar missão: {exc.errors()[0]['msg']}"

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
        return f"Senhor, o Budget Guard bloqueou a delegação: {exc}"
    except ValueError as exc:
        return f"Não foi possível delegar a missão: {exc}"

    if params.abrir_escritorio:
        orch.emit_office_command("open", profile=params.perfil, view_mode="office3d")

    if job.deduplicated:
        return (
            f"Senhor, uma missão idêntica já foi registrada recentemente (idempotência ativa). "
            f"Job existente: {job.job_id[:8]} (agente '{job.profile}', status: {job.status})."
        )

    if job.status == "awaiting_approval":
        return (
            f"Senhor, por conter contexto externo não confiável, a missão "
            f"{job.job_id[:8]} para o agente '{job.profile}' aguarda sua aprovação explícita Tier 3 "
            f"(aprovação ID: {job.approval_id})."
        )

    return (
        f"Missão iniciada em segundo plano com o agente '{job.profile}', senhor "
        f"(ID #{job.job_id[:8]}, status: {job.status})."
    )


def consultar_status_agentes(
    perfil: Literal["pesquisador", "organizador", "ideias", "engenheiro"] | None = None,
    job_id: str | None = None,
) -> str:
    """Consulta o andamento das missões ou retorna o último resultado concluído de um agente."""
    try:
        params = ConsultarStatusAgentesParams(perfil=perfil, job_id=job_id)
    except ValidationError as exc:
        return f"Parâmetros inválidos ao consultar agentes: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    if params.job_id or params.perfil:
        job = orch.resolve_target_job(job_id=params.job_id, profile=params.perfil)
        if job is None:
            alvo = params.job_id or params.perfil
            return f"Senhor, não encontrei missões recentes para '{alvo}'."
        extra = ""
        if job.result:
            extra = f"\nResultado ({job.kb_status}): {job.result[:650]}"
        elif job.error:
            extra = f"\nErro: {job.error[:240]}"
        return (
            f"Agente '{job.profile}' (#{job.job_id[:8]}): status={job.status}, "
            f"progresso={job.progress_pct}%, tarefa='{job.task}'.{extra}"
        )

    snapshot = orch.get_status()
    budget = snapshot["budget"]
    active = snapshot["active_jobs"]
    all_jobs = snapshot["jobs"]
    pending_approvals = snapshot["pending_approvals"]

    resumo_ativos = (
        "; ".join(f"{j['profile']} ({j['progress_pct']}%)" for j in active[:4])
        if active
        else "nenhum em execução"
    )
    concluidos = [j for j in all_jobs if j["status"] == "completed"]
    ultimo_txt = ""
    if concluidos:
        ult = concluidos[0]
        trecho = str(ult.get("result") or "")[:300].replace("\n", " ")
        ultimo_txt = f" Último concluído: {ult['profile']} (#{ult['job_id'][:8]}, {ult.get('kb_status')}) -> {trecho}"

    return (
        f"Senhor, agentes ativos: {budget['active_concurrent']}/{budget['max_concurrent_agents']} ({resumo_ativos}). "
        f"Orçamento diário: US$ {budget['daily_usd_used']:.4f} / US$ {budget['max_usd_per_day']:.2f} "
        f"({budget['daily_tokens_used']} tokens). Aprovações Tier 3 pendentes: {len(pending_approvals)}.{ultimo_txt}"
    )


def curar_resultado_agente(
    acao: Literal["indexar", "descartar"],
    perfil: Literal["pesquisador", "organizador", "ideias", "engenheiro"] | None = None,
    job_id: str | None = None,
    titulo: str | None = None,
) -> str:
    """Indexa na Base de Conhecimento da F.R.Y.I.Vs ou descarta o resultado de uma missão de agente."""
    try:
        params = CurarResultadoAgenteParams(
            acao=acao,
            perfil=perfil,
            job_id=job_id,
            titulo=titulo,
        )
    except ValidationError as exc:
        return f"Parâmetros inválidos na curadoria do agente: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    target = orch.resolve_target_job(
        job_id=params.job_id,
        profile=params.perfil,
        only_completed=(params.acao == "indexar"),
    )
    if target is None:
        alvo = params.perfil or params.job_id or "recente"
        return f"Senhor, não encontrei resultado disponível do agente ({alvo}) para {params.acao}."

    if params.acao == "descartar":
        orch.discard_job(target.job_id, actor="fryivs_skill")
        return (
            f"Resultado da missão #{target.job_id[:8]} do agente '{target.profile}' "
            f"descartado com sucesso, senhor."
        )

    try:
        res = orch.index_job_to_kb(
            target.job_id,
            titulo=params.titulo or target.task[:110],
            actor="fryivs_skill",
        )
    except (KeyError, ValueError) as exc:
        return f"Não foi possível indexar o resultado na Base de Conhecimento, senhor: {exc}"

    chunks = res.get("kb_info", {}).get("chunks_indexados", 1)
    return (
        f"Conhecimento do agente '{target.profile}' indexado na minha Base de Conhecimento "
        f"com sucesso ({chunks} chunk(s) salvos), senhor."
    )


def controlar_escritorio_agentes(
    acao: OfficeActionType,
    perfil: Literal["pesquisador", "organizador", "ideias", "engenheiro"] | None = None,
    atividade: OfficeActivityType | None = None,
) -> str:
    """Controla visualmente o Escritório 3D dos Agentes na interface (abrir, fechar, focar, festa ou atividade)."""
    try:
        params = ControlarEscritorioAgentesParams(
            acao=acao,
            perfil=perfil,
            atividade=atividade,
        )
    except ValidationError as exc:
        return f"Parâmetros inválidos para controlar o Escritório 3D: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    action_map = {
        "abrir": ("open", "office3d", "Escritório 3D dos Agentes aberto na tela, senhor."),
        "fechar": ("close", None, "Escritório dos Agentes fechado, senhor."),
        "focar": (
            "focus",
            "office3d",
            f"Focando no agente '{params.perfil or 'pesquisador'}' no Escritório 3D, senhor.",
        ),
        "festa": ("party", "office3d", "Modo festa ativado no Escritório dos Agentes, senhor!"),
        "atividade": (
            "activity",
            "office3d",
            f"Atividade '{params.atividade or 'coffee'}' acionada no Escritório 3D, senhor.",
        ),
        "fila": ("open", "list", "Fila de missões dos agentes aberta na tela, senhor."),
    }
    evt_action, view_mode, msg = action_map[params.acao]
    orch.emit_office_command(
        evt_action,
        profile=params.perfil,
        activity=params.atividade or ("coffee" if params.acao == "atividade" else None),
        view_mode=view_mode,
    )
    return msg


def cancelar_missao_agente(
    perfil: Literal["pesquisador", "organizador", "ideias", "engenheiro"] | None = None,
    job_id: str | None = None,
    cancelar_todos: bool = False,
) -> str:
    """Cancela uma missão específica (por ID ou nome do agente) ou aciona o Kill-Switch global."""
    try:
        params = CancelarMissaoAgenteParams(
            perfil=perfil,
            job_id=job_id,
            cancelar_todos=cancelar_todos,
        )
    except ValidationError as exc:
        return f"Parâmetros inválidos ao cancelar missão: {exc.errors()[0]['msg']}"

    orch = get_orchestrator()
    if params.cancelar_todos or (params.job_id and params.job_id.strip().lower() in ("all", "todos")):
        res = orch.kill_all_jobs(actor="fryivs_skill", reason="kill_switch_voice_or_skill")
        return (
            f"Kill-Switch acionado, senhor. {res['killed_count']} missão(ões) encerrada(s) "
            f"imediatamente e todos os slots de concorrência liberados."
        )

    target = orch.resolve_target_job(job_id=params.job_id, profile=params.perfil, only_active=True)
    if target is None and params.job_id:
        target = orch.resolve_target_job(job_id=params.job_id)

    if target is None:
        if not params.job_id and not params.perfil:
            return (
                "Senhor, informe o agente ('pesquisador', 'organizador', 'ideias' ou 'engenheiro'), "
                "o 'job_id' ou peça para encerrar todos os agentes."
            )
        return f"Senhor, não encontrei missão ativa para '{params.perfil or params.job_id}'."

    job = orch.cancel_job(target.job_id, actor="fryivs_skill", reason="cancelled_by_skill")
    if job is None:
        return f"Senhor, não localizei a missão '{target.job_id}'."
    return f"Missão #{job.job_id[:8]} do agente '{job.profile}' cancelada com sucesso, senhor."


def listar_perfis_hermes() -> str:
    """Lista os 4 agentes especialistas disponíveis na F.R.Y.I.Vs."""
    ListarPerfisHermesParams()
    linhas = [
        f"- {cfg['name']} ({cfg['label']}): {cfg['mission']}"
        for cfg in HERMES_PROFILES.values()
    ]
    return "Agentes especialistas disponíveis:\n" + "\n".join(linhas)


HERMES_SKILLS_REGISTRY: Final[dict[str, Callable[..., str]]] = {
    "delegar_missao_hermes": delegar_missao_hermes,
    "consultar_status_agentes": consultar_status_agentes,
    "curar_resultado_agente": curar_resultado_agente,
    "controlar_escritorio_agentes": controlar_escritorio_agentes,
    "cancelar_missao_agente": cancelar_missao_agente,
    "listar_perfis_hermes": listar_perfis_hermes,
}


HERMES_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "delegar_missao_hermes",
            "description": (
                "Delega uma missão em segundo plano para um dos 4 agentes especialistas da IA "
                "('pesquisador', 'organizador', 'ideias' ou 'engenheiro')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "perfil": {
                        "type": "string",
                        "enum": ["pesquisador", "organizador", "ideias", "engenheiro"],
                        "description": "Agente especialista que executará a missão.",
                    },
                    "missao": {
                        "type": "string",
                        "description": "Objetivo completo da missão para o agente.",
                    },
                    "contexto": {
                        "type": "string",
                        "description": "Contexto opcional.",
                    },
                    "contexto_externo": {
                        "type": "boolean",
                        "description": "True apenas se o contexto vier de fonte externa não confiável.",
                    },
                    "abrir_escritorio": {
                        "type": "boolean",
                        "description": "True se o usuário também pediu para abrir/ver o Escritório 3D.",
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
                "Consulta o status e lê os resultados concluídos dos agentes especialistas "
                "('pesquisador', 'organizador', 'ideias', 'engenheiro')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "perfil": {
                        "type": "string",
                        "enum": ["pesquisador", "organizador", "ideias", "engenheiro"],
                        "description": "Filtra pelo agente desejado para ler o andamento ou último resultado.",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "ID opcional da missão.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "curar_resultado_agente",
            "description": (
                "Indexa na Base de Conhecimento da F.R.Y.I.Vs ('indexar') ou descarta ('descartar') "
                "o resultado produzido por um agente especialista."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "enum": ["indexar", "descartar"],
                        "description": "'indexar' para salvar na Base de Conhecimento ou 'descartar' para remover.",
                    },
                    "perfil": {
                        "type": "string",
                        "enum": ["pesquisador", "organizador", "ideias", "engenheiro"],
                        "description": "Agente autor do resultado (opcional: se omitido usa o mais recente).",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "ID opcional da missão.",
                    },
                    "titulo": {
                        "type": "string",
                        "description": "Título opcional para salvar na Base de Conhecimento.",
                    },
                },
                "required": ["acao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "controlar_escritorio_agentes",
            "description": (
                "Abre ou fecha o Escritório 3D dos Agentes na tela, foca em um agente específico, "
                "ativa festa ou comanda uma atividade no escritório ('coffee', 'pingpong', 'game', 'band', 'dance', 'chat', 'plant')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "enum": ["abrir", "fechar", "focar", "festa", "atividade", "fila"],
                        "description": "Ação visual no painel/Escritório 3D dos Agentes.",
                    },
                    "perfil": {
                        "type": "string",
                        "enum": ["pesquisador", "organizador", "ideias", "engenheiro"],
                        "description": "Agente alvo quando acao for 'focar'.",
                    },
                    "atividade": {
                        "type": "string",
                        "enum": ["coffee", "pingpong", "game", "band", "dance", "chat", "plant"],
                        "description": "Atividade social dos agentes livres quando acao for 'atividade'.",
                    },
                },
                "required": ["acao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancelar_missao_agente",
            "description": "Cancela a missão ativa de um agente ou aciona o Kill-Switch encerrando todos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "perfil": {
                        "type": "string",
                        "enum": ["pesquisador", "organizador", "ideias", "engenheiro"],
                        "description": "Agente cuja missão em andamento deve ser interrompida.",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "ID da missão (ou 'all' para todas).",
                    },
                    "cancelar_todos": {
                        "type": "boolean",
                        "description": "True para encerrar imediatamente todos os agentes ativos.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_perfis_hermes",
            "description": "Lista os 4 agentes especialistas disponíveis (pesquisador, organizador, ideias e engenheiro).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
