"""
Skills de Automação Corporativa n8n para a assistente F.R.Y.I.Vs.

Expõe 3 skills tipadas com Pydantic para acionar workflows corporativos via webhooks
assinados (HMAC-SHA256 + SSRF Guard), listar workflows e consultar execuções recentes
na instância n8n configurada.
"""

from __future__ import annotations

import json
from typing import Any, Final, Literal
from pydantic import BaseModel, Field, ValidationError

from core.n8n_bridge import get_n8n_bridge


class DispararWorkflowN8nParams(BaseModel):
    acao: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Ação do hub n8n ('briefing', 'alert', 'status', 'custom') ou nome lógico do fluxo.",
    )
    dados: dict[str, Any] | str | None = Field(
        default=None,
        description="Objeto JSON (ou string JSON) com parâmetros adicionais para o workflow n8n.",
    )
    webhook_url: str | None = Field(
        default=None,
        description="URL completa ou caminho de webhook n8n opcional (usa N8N_WEBHOOK_URL/N8N_BASE_URL se omitido).",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Identificador de correlação opcional para rastreamento ponta a ponta.",
    )


class ListarWorkflowsN8nParams(BaseModel):
    apenas_ativos: bool = Field(
        default=False,
        description="Se True, lista apenas workflows publicados/ativos no n8n.",
    )
    tag: str | None = Field(
        default=None,
        description="Filtro opcional por tag do workflow (ex: 'fryivs', 'webhook', 'briefing').",
    )
    limite: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Quantidade máxima de workflows retornados (1 a 100).",
    )


class ConsultarExecucoesN8nParams(BaseModel):
    workflow_id: str | None = Field(
        default=None,
        description="ID opcional de um workflow específico para filtrar as execuções.",
    )
    status: Literal["success", "error", "running", "waiting", "crashed"] | None = Field(
        default=None,
        description="Status opcional da execução ('success', 'error', 'running', 'waiting', 'crashed').",
    )
    limite: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Quantidade máxima de execuções recentes retornadas (1 a 50).",
    )


def _normalizar_dados(dados: dict[str, Any] | str | None) -> dict[str, Any]:
    if dados is None:
        return {}
    if isinstance(dados, dict):
        return dados
    texto = str(dados).strip()
    if not texto:
        return {}
    try:
        parsed = json.loads(texto)
        if isinstance(parsed, dict):
            return parsed
        return {"valor": parsed}
    except json.JSONDecodeError:
        return {"mensagem": texto}


def disparar_workflow_n8n(
    acao: str,
    dados: dict[str, Any] | str | None = None,
    webhook_url: str | None = None,
    correlation_id: str | None = None,
) -> str:
    """
    Dispara um workflow corporativo no n8n via webhook assinado com HMAC-SHA256 e validação SSRF.
    """
    try:
        params = DispararWorkflowN8nParams(
            acao=acao,
            dados=dados,
            webhook_url=webhook_url,
            correlation_id=correlation_id,
        )
    except ValidationError as exc:
        return f"Erro nos parâmetros de disparo n8n: {exc.errors()[0].get('msg', str(exc))}"

    payload = _normalizar_dados(params.dados)
    bridge = get_n8n_bridge()
    res = bridge.trigger_webhook(
        action=params.acao,
        payload=payload,
        webhook_url=params.webhook_url,
        correlation_id=params.correlation_id,
    )

    if not res.get("ok"):
        return f"Falha ao disparar workflow n8n ('{params.acao}'): {res.get('error', 'erro desconhecido')}."

    corr = res.get("correlation_id", "")
    status_code = res.get("status_code", 200)
    signed_label = "assinado HMAC-SHA256" if res.get("signed") else "sem assinatura HMAC"
    data = res.get("data")
    resumo_dado = ""
    if isinstance(data, dict):
        msg = data.get("message") or data.get("summary") or data.get("status")
        if msg:
            resumo_dado = f" Resposta: {str(msg)[:180]}."
    elif isinstance(data, str) and data.strip():
        resumo_dado = f" Resposta: {data.strip()[:180]}."

    return (
        f"Workflow n8n '{params.acao}' acionado com sucesso "
        f"(HTTP {status_code}, {signed_label}, correlation_id={corr}).{resumo_dado}"
    )


def listar_workflows_n8n(
    apenas_ativos: bool = False,
    tag: str | None = None,
    limite: int = 20,
) -> str:
    """
    Lista workflows disponíveis na instância n8n configurada via REST API v1.
    """
    try:
        params = ListarWorkflowsN8nParams(
            apenas_ativos=apenas_ativos,
            tag=tag,
            limite=limite,
        )
    except ValidationError as exc:
        return f"Erro nos parâmetros de listagem n8n: {exc.errors()[0].get('msg', str(exc))}"

    res = get_n8n_bridge().list_workflows(
        active_only=params.apenas_ativos,
        tag=params.tag,
        limit=params.limite,
    )
    if not res.get("ok"):
        return f"Não foi possível listar workflows n8n: {res.get('error', 'erro desconhecido')}."

    workflows = res.get("workflows") or []
    if not workflows:
        filtro = f" com tag '{params.tag}'" if params.tag else ""
        return f"Nenhum workflow encontrado no n8n{filtro}."

    linhas = []
    for wf in workflows:
        estado = "ativo" if wf.get("active") else "rascunho"
        tags_txt = f" [{', '.join(wf['tags'])}]" if wf.get("tags") else ""
        linhas.append(f"- {wf['name']} (ID: {wf['id']}, {estado}){tags_txt}")
    return f"Workflows n8n encontrados ({len(workflows)}):\n" + "\n".join(linhas)


def consultar_execucoes_n8n(
    workflow_id: str | None = None,
    status: str | None = None,
    limite: int = 10,
) -> str:
    """
    Consulta execuções recentes de workflows na instância n8n via REST API v1.
    """
    try:
        params = ConsultarExecucoesN8nParams(
            workflow_id=workflow_id,
            status=status,  # type: ignore[arg-type]
            limite=limite,
        )
    except ValidationError as exc:
        return f"Erro nos parâmetros de consulta de execuções n8n: {exc.errors()[0].get('msg', str(exc))}"

    res = get_n8n_bridge().list_executions(
        workflow_id=params.workflow_id,
        status=params.status,
        limit=params.limite,
    )
    if not res.get("ok"):
        return f"Não foi possível consultar execuções n8n: {res.get('error', 'erro desconhecido')}."

    executions = res.get("executions") or []
    if not executions:
        return "Nenhuma execução n8n encontrada para os filtros informados."

    linhas = []
    for ex in executions:
        linhas.append(
            f"- Execução #{ex['id']} (workflow={ex['workflowId']}, status={ex['status']}, início={ex.get('startedAt') or 'N/A'})"
        )
    return f"Execuções recentes no n8n ({len(executions)}):\n" + "\n".join(linhas)


N8N_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "disparar_workflow_n8n",
            "description": (
                "Dispara um workflow corporativo no n8n (briefing, alerta, status ou automação externa) "
                "via webhook assinado com HMAC-SHA256 e validação SSRF."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "description": "Ação do hub n8n ('briefing', 'alert', 'status', 'custom') ou nome do fluxo.",
                    },
                    "dados": {
                        "type": "object",
                        "description": "Dados estruturados opcionais enviados no payload do workflow.",
                    },
                    "webhook_url": {
                        "type": "string",
                        "description": "URL ou caminho opcional de webhook n8n (usa padrão configurado se omitido).",
                    },
                    "correlation_id": {
                        "type": "string",
                        "description": "ID de correlação opcional para rastreamento distribuído.",
                    },
                },
                "required": ["acao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_workflows_n8n",
            "description": "Lista os workflows cadastrados na instância n8n corporativa (com filtros opcionais por status ativo e tag).",
            "parameters": {
                "type": "object",
                "properties": {
                    "apenas_ativos": {
                        "type": "boolean",
                        "description": "Filtrar somente workflows ativos/publicados.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag opcional para filtrar workflows (ex: 'fryivs', 'briefing', 'webhook').",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Número máximo de workflows retornados (padrão 20).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_execucoes_n8n",
            "description": "Consulta o histórico de execuções recentes dos workflows no n8n (status success, error, running, waiting).",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "ID opcional do workflow para filtrar execuções.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["success", "error", "running", "waiting", "crashed"],
                        "description": "Filtro opcional pelo status da execução.",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Número máximo de execuções retornadas (padrão 10).",
                    },
                },
            },
        },
    },
]
