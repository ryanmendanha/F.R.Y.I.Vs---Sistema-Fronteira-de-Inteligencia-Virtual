"""
Motor de Políticas (Policy Tiers), Taint-Tracking e Auditoria Imutável (JSONL) da F.R.Y.I.Vs.

Implementa os controles obrigatórios da Camada 0 (Governança Multi-Agente):
- Classificação de ferramentas/ações em 3 níveis:
  - Tier 1 (Leitura / Consulta): execução livre em sessão E2EE ativa.
  - Tier 2 (Mutação Local Reversível): execução automática com registro em auditoria.
  - Tier 3 (Irreversível / Externa / Financeira / Shell / Webhook): exige aprovação
    explícita Human-in-the-Loop (ApprovalRequest com UUID).
- Regra de Taint-Tracking:
  - Se `context_tainted=True` (contexto contém trechos externos web/RAG não confiáveis),
    qualquer ferramenta Tier 2 ou Tier 3 (mutação, exfiltração ou destrutiva) é elevada
    automaticamente para exigir aprovação explícita Human-in-the-Loop.
- Audit Log Imutável (JSONL, append-only + hash chain SHA-256) em `data/audit_log.jsonl`
  (caminho configurável para testes), com redação automática de segredos antes da escrita.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal


class PolicyTier(IntEnum):
    """Níveis hierárquicos de risco e autorização de ações na F.R.Y.I.Vs."""

    TIER_1_READ = 1
    TIER_2_MUTATION = 2
    TIER_3_CRITICAL = 3


ApprovalStatus = Literal["pending", "approved", "denied", "expired"]

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "audit_log.jsonl"
DEFAULT_APPROVAL_TTL_SECONDS = 600.0


# =============================================================================
# Redação Automática de Segredos (antes de gravar auditoria ou aprovações)
# =============================================================================

REDACTED_PLACEHOLDER = "[REDACTED]"

_SENSITIVE_KEY_TOKENS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "senha",
        "secret",
        "hmac_secret",
        "hermes_hmac_secret",
        "n8n_hmac_secret",
        "api_key",
        "apikey",
        "gemini_api_key",
        "openai_api_key",
        "hermes_api_key",
        "n8n_api_key",
        "access_token",
        "refresh_token",
        "auth_token",
        "session_token",
        "private_key",
        "authorization",
        "x-e2ee-session",
        "x-fryivs-signature",
        "client_secret",
        "credential",
        "credentials",
        "bearer",
    }
)

_SECRET_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Google / Gemini API keys (AIza...)
    (re.compile(r"AIza[0-9A-Za-z\-_]{10,}"), REDACTED_PLACEHOLDER),
    # OpenAI / Anthropic / OpenRouter / Stripe keys (sk-...)
    (
        re.compile(r"\bsk-(?:proj-|ant-|or-v1-|live-|test-)?[0-9A-Za-z\-_]{10,}\b"),
        REDACTED_PLACEHOLDER,
    ),
    # GitHub tokens
    (re.compile(r"\b(?:gh[pousr]_[0-9A-Za-z]{16,}|github_pat_[0-9A-Za-z_]{16,})\b"), REDACTED_PLACEHOLDER),
    # Slack tokens
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"), REDACTED_PLACEHOLDER),
    # AWS access key IDs
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED_PLACEHOLDER),
    # JWTs
    (
        re.compile(r"\beyJ[A-Za-z0-9\-_]{8,}\.eyJ[A-Za-z0-9\-_]{8,}\.[A-Za-z0-9\-_]{8,}\b"),
        REDACTED_PLACEHOLDER,
    ),
    # Authorization Bearer / Basic headers
    (
        re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9\-._~+/=]{6,}"),
        r"\1" + REDACTED_PLACEHOLDER,
    ),
    (
        re.compile(r"(?i)\b(Basic\s+)[A-Za-z0-9+/=]{6,}"),
        r"\1" + REDACTED_PLACEHOLDER,
    ),
    # HMAC hex signatures (sha256=<hex>)
    (
        re.compile(r"(?i)\b(sha256=)[0-9a-f]{32,}\b"),
        r"\1" + REDACTED_PLACEHOLDER,
    ),
    # Key-value pairs in text/JSON/env/query strings
    (
        re.compile(
            r"(?i)(\b(?:password|passwd|pwd|senha|hmac_secret|hermes_hmac_secret|"
            r"n8n_hmac_secret|opencode_server_password|fryivs_voice_password|"
            r"api_key|apikey|secret_key|secret|access_token|refresh_token|"
            r"auth_token|session_token|private_key|x-e2ee-session)\b"
            r"""\s*["']?\s*[:=]\s*["']?)([^\s"',;}\]&]+)"""
        ),
        r"\1" + REDACTED_PLACEHOLDER,
    ),
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in _SENSITIVE_KEY_TOKENS or key.strip().lower() in _SENSITIVE_KEY_TOKENS:
        return True
    return any(
        marker in normalized
        for marker in ("password", "passwd", "senha", "secret", "api_key", "apikey", "private_key", "token")
    )


def redact_secrets(value: Any) -> Any:
    """
    Redige recursivamente segredos (AIza..., sk-..., Bearer ..., senhas, HMAC secrets,
    JWTs e campos sensíveis) em strings, dicionários e listas antes da persistência.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        sanitized = value
        for pattern, replacement in _SECRET_TEXT_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            if _is_sensitive_key(key_str):
                result[key_str] = REDACTED_PLACEHOLDER
            else:
                result[key_str] = redact_secrets(v)
        return result

    if isinstance(value, (list, tuple, set)):
        redacted_items = [redact_secrets(item) for item in value]
        if isinstance(value, tuple):
            return tuple(redacted_items)
        return redacted_items

    return redact_secrets(str(value))


def summarize_args(args: dict[str, Any] | None, max_length: int = 240) -> str:
    """Gera resumo compacto e redigido dos argumentos de uma ferramenta."""
    if not args:
        return "{}"
    sanitized = redact_secrets(copy.deepcopy(args))
    try:
        rendered = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        rendered = redact_secrets(str(sanitized))
    if len(rendered) > max_length:
        return rendered[: max_length - 3] + "..."
    return rendered


# =============================================================================
# Classificação de Ferramentas por Policy Tier
# =============================================================================

_DEFAULT_TOOL_TIERS: dict[str, PolicyTier] = {
    # Tier 1: Leitura / Consulta (sem efeitos colaterais destrutivos ou externos)
    "obter_hora_data": PolicyTier.TIER_1_READ,
    "status_sistema": PolicyTier.TIER_1_READ,
    "listar_janelas": PolicyTier.TIER_1_READ,
    "tirar_screenshot": PolicyTier.TIER_1_READ,
    "ler_texto_da_tela": PolicyTier.TIER_1_READ,
    "consultar_planilha": PolicyTier.TIER_1_READ,
    "ler_documento_word": PolicyTier.TIER_1_READ,
    "listar_agendamentos": PolicyTier.TIER_1_READ,
    "consultar_mapa_codigo": PolicyTier.TIER_1_READ,
    "explicar_modulo_grafo": PolicyTier.TIER_1_READ,
    "caminho_entre_componentes": PolicyTier.TIER_1_READ,
    "resumo_arquitetura_sistema": PolicyTier.TIER_1_READ,
    "ler_conteudo_pagina": PolicyTier.TIER_1_READ,
    "capturar_tela_web": PolicyTier.TIER_1_READ,
    "pesquisar_google": PolicyTier.TIER_1_READ,
    "pesquisar_informacao_web": PolicyTier.TIER_1_READ,
    "pesquisar_youtube": PolicyTier.TIER_1_READ,
    "pesquisar_na_web": PolicyTier.TIER_1_READ,
    "consultar_status_agentes": PolicyTier.TIER_1_READ,
    "listar_perfis_hermes": PolicyTier.TIER_1_READ,
    "listar_workflows_n8n": PolicyTier.TIER_1_READ,
    "consultar_execucoes_n8n": PolicyTier.TIER_1_READ,
    "buscar_conhecimento": PolicyTier.TIER_1_READ,
    "buscar_memoria": PolicyTier.TIER_1_READ,
    # Tier 2: Mutação Local Reversível
    "abrir_programa": PolicyTier.TIER_2_MUTATION,
    "focar_janela": PolicyTier.TIER_2_MUTATION,
    "minimizar_janela": PolicyTier.TIER_2_MUTATION,
    "maximizar_janela": PolicyTier.TIER_2_MUTATION,
    "fechar_janela": PolicyTier.TIER_2_MUTATION,
    "controlar_volume": PolicyTier.TIER_2_MUTATION,
    "digitar_texto": PolicyTier.TIER_2_MUTATION,
    "pressionar_atalho": PolicyTier.TIER_2_MUTATION,
    "navegar_para": PolicyTier.TIER_2_MUTATION,
    "clicar_elemento_web": PolicyTier.TIER_2_MUTATION,
    "interagir_pagina_web": PolicyTier.TIER_2_MUTATION,
    "digitar_campo_web": PolicyTier.TIER_2_MUTATION,
    "fechar_navegador": PolicyTier.TIER_2_MUTATION,
    "localizar_e_clicar_imagem": PolicyTier.TIER_2_MUTATION,
    "criar_planilha": PolicyTier.TIER_2_MUTATION,
    "editar_planilha": PolicyTier.TIER_2_MUTATION,
    "abrir_planilha": PolicyTier.TIER_2_MUTATION,
    "criar_documento_word": PolicyTier.TIER_2_MUTATION,
    "editar_documento_word": PolicyTier.TIER_2_MUTATION,
    "abrir_documento_word": PolicyTier.TIER_2_MUTATION,
    "atualizar_mapa_codigo": PolicyTier.TIER_2_MUTATION,
    "agendar_execucao": PolicyTier.TIER_2_MUTATION,
    "gerenciar_arquivos": PolicyTier.TIER_2_MUTATION,
    "delegar_missao_hermes": PolicyTier.TIER_2_MUTATION,
    "cancelar_missao_agente": PolicyTier.TIER_2_MUTATION,
    # Tier 3: Irreversível / Externa / Financeira / Shell / Webhook
    "enviar_alerta_webhook": PolicyTier.TIER_3_CRITICAL,
    "bloquear_tela": PolicyTier.TIER_3_CRITICAL,
    "disparar_workflow_n8n": PolicyTier.TIER_3_CRITICAL,
    "executar_comando_shell": PolicyTier.TIER_3_CRITICAL,
    "shell_exec": PolicyTier.TIER_3_CRITICAL,
    "run_shell": PolicyTier.TIER_3_CRITICAL,
    "bash": PolicyTier.TIER_3_CRITICAL,
    "powershell": PolicyTier.TIER_3_CRITICAL,
    "deletar_arquivo": PolicyTier.TIER_3_CRITICAL,
    "delete_file": PolicyTier.TIER_3_CRITICAL,
    "enviar_email": PolicyTier.TIER_3_CRITICAL,
    "send_email": PolicyTier.TIER_3_CRITICAL,
    "enviar_whatsapp": PolicyTier.TIER_3_CRITICAL,
    "send_whatsapp": PolicyTier.TIER_3_CRITICAL,
    "transferencia_bancaria": PolicyTier.TIER_3_CRITICAL,
    "processar_pagamento": PolicyTier.TIER_3_CRITICAL,
    "http_post": PolicyTier.TIER_3_CRITICAL,
    "http_exfiltrate": PolicyTier.TIER_3_CRITICAL,
}

_TIER_3_KEYWORDS: tuple[str, ...] = (
    "delete",
    "deletar",
    "apagar",
    "excluir",
    "remover",
    "purge",
    "drop_",
    "wipe",
    "format_",
    "shell",
    "bash",
    "powershell",
    "cmd_exec",
    "terminal_exec",
    "subprocess",
    "webhook",
    "exfiltrat",
    "email",
    "gmail",
    "smtp",
    "whatsapp",
    "telegram",
    "slack",
    "sms",
    "payment",
    "pagar",
    "pagamento",
    "pix",
    "transfer",
    "bank",
    "bancari",
    "finance",
    "invoice",
    "fatura",
    "billing",
    "deploy",
    "publish",
    "erp_",
    "crm_",
    "enviar_",
    "send_",
    "disparar_",
)

_TIER_1_PREFIXES: tuple[str, ...] = (
    "listar_",
    "consultar_",
    "ler_",
    "obter_",
    "explicar_",
    "resumo_",
    "status_",
    "caminho_",
    "buscar_",
    "pesquisar_",
    "get_",
    "list_",
    "read_",
    "query_",
    "search_",
    "check_",
    "inspect_",
)

_DESTRUCTIVE_ARG_ACTIONS: frozenset[str] = frozenset(
    {
        "deletar",
        "delete",
        "apagar",
        "excluir",
        "remover",
        "remove",
        "rm",
        "unlink",
        "rmdir",
        "purge",
        "wipe",
        "destroy",
        "format",
    }
)

_READONLY_ARG_ACTIONS: frozenset[str] = frozenset(
    {"listar", "list", "ler", "read", "info", "exists", "buscar", "search", "inspect"}
)


# =============================================================================
# Estruturas de Aprovação e Decisão
# =============================================================================


@dataclass
class ApprovalRequest:
    """Solicitação explícita Human-in-the-Loop para ações Tier 3 ou elevadas por taint."""

    approval_id: str
    tool: str
    tier: int
    args_summary: str
    created_at: float
    expires_at: float
    status: ApprovalStatus = "pending"
    actor: str = "user"
    agent: str = "fryivs"
    correlation_id: str = ""
    reason: str = ""
    context_tainted: bool = False
    decided_at: float | None = None
    decided_by: str | None = None
    decision_note: str = ""

    def is_expired(self, now: float | None = None) -> bool:
        ts = time.time() if now is None else now
        return self.status == "expired" or (self.status == "pending" and ts >= self.expires_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "tool": self.tool,
            "tier": int(self.tier),
            "args_summary": self.args_summary,
            "created_at": self.created_at,
            "created_at_iso": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "expires_at": self.expires_at,
            "expires_at_iso": datetime.fromtimestamp(self.expires_at, tz=timezone.utc).isoformat(),
            "status": self.status,
            "actor": self.actor,
            "agent": self.agent,
            "correlation_id": self.correlation_id,
            "reason": self.reason,
            "context_tainted": self.context_tainted,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_note": self.decision_note,
        }


@dataclass
class PolicyDecision:
    """Resultado determinístico da avaliação de política de uma ação/ferramenta."""

    allowed: bool
    requires_approval: bool
    tier: PolicyTier
    effective_tier: PolicyTier
    taint_elevated: bool
    reason: str
    approval_request: ApprovalRequest | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "tier": int(self.tier),
            "effective_tier": int(self.effective_tier),
            "taint_elevated": self.taint_elevated,
            "reason": self.reason,
            "approval_request": self.approval_request.to_dict() if self.approval_request else None,
        }


# =============================================================================
# Audit Log Imutável (JSONL append-only + hash chain + secret redaction)
# =============================================================================


class AuditLogger:
    """
    Registrador de auditoria imutável em formato JSON Lines (JSONL).

    - Append-only com lock de thread.
    - Redação automática de segredos em TODOS os campos antes da persistência.
    - Encadeamento criptográfico SHA-256 (`prev_hash` -> `entry_hash`) para detecção
      de adulteração retroativa do arquivo.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, log_path: str | Path | None = None) -> None:
        if log_path is not None:
            self._path = Path(log_path)
        else:
            env_path = os.environ.get("FRYIVS_AUDIT_LOG_PATH", "").strip()
            self._path = Path(env_path) if env_path else DEFAULT_AUDIT_LOG_PATH
        self._lock = threading.Lock()
        self._last_hash: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    def _load_last_hash_locked(self) -> str:
        if self._last_hash is not None:
            return self._last_hash
        if not self._path.exists() or self._path.stat().st_size == 0:
            self._last_hash = self.GENESIS_HASH
            return self._last_hash
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                last_line = ""
                for line in fh:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
                if last_line:
                    parsed = json.loads(last_line)
                    entry_hash = parsed.get("entry_hash")
                    if isinstance(entry_hash, str) and len(entry_hash) == 64:
                        self._last_hash = entry_hash
                        return self._last_hash
        except Exception:
            pass
        self._last_hash = self.GENESIS_HASH
        return self._last_hash

    @staticmethod
    def _compute_entry_hash(record_without_hash: dict[str, Any]) -> str:
        canonical = json.dumps(
            record_without_hash,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def log(
        self,
        *,
        actor: str,
        agent: str,
        tool: str,
        tier: int | PolicyTier,
        correlation_id: str,
        status: str,
        tokens: int = 0,
        duration_ms: float = 0.0,
        details: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        """Grava um registro imutável redigido no arquivo JSONL e retorna o evento gravado."""
        now_iso = datetime.now(timezone.utc).isoformat()
        base_record: dict[str, Any] = {
            "timestamp": now_iso,
            "actor": str(redact_secrets(actor or "system")),
            "agent": str(redact_secrets(agent or "fryivs")),
            "tool": str(redact_secrets(tool or "unknown")),
            "tier": int(tier),
            "correlation_id": str(redact_secrets(correlation_id or "")),
            "status": str(redact_secrets(status or "unknown")),
            "tokens": max(0, int(tokens)),
            "duration_ms": round(max(0.0, float(duration_ms)), 3),
        }
        if details is not None:
            base_record["details"] = redact_secrets(details)

        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            prev_hash = self._load_last_hash_locked()
            base_record["prev_hash"] = prev_hash
            entry_hash = self._compute_entry_hash(base_record)
            record = dict(base_record)
            record["entry_hash"] = entry_hash

            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
            self._last_hash = entry_hash
            return record

    def read_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lê os últimos `limit` registros do log de auditoria."""
        with self._lock:
            if not self._path.exists():
                return []
            records: list[dict[str, Any]] = []
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        records.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        continue
            if limit <= 0:
                return []
            return records[-limit:]

    def verify_integrity(self) -> tuple[bool, str]:
        """Verifica a integridade da cadeia SHA-256 de todas as linhas do JSONL."""
        with self._lock:
            if not self._path.exists():
                return True, "Audit log ainda vazio."
            expected_prev = self.GENESIS_HASH
            count = 0
            with self._path.open("r", encoding="utf-8") as fh:
                for line_no, raw_line in enumerate(fh, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        entry = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        return False, f"Linha {line_no} com JSON corrompido: {exc}"
                    if entry.get("prev_hash") != expected_prev:
                        return False, f"Quebra de encadeamento prev_hash na linha {line_no}."
                    stored_hash = entry.get("entry_hash")
                    payload = {k: v for k, v in entry.items() if k != "entry_hash"}
                    recomputed = self._compute_entry_hash(payload)
                    if stored_hash != recomputed:
                        return False, f"Hash adulterado detectado na linha {line_no}."
                    expected_prev = recomputed
                    count += 1
            return True, f"Integridade verificada ({count} registros)."


# =============================================================================
# Motor de Políticas (PolicyEngine)
# =============================================================================


class PolicyEngine:
    """
    Avaliador de políticas por Tier com Taint-Tracking, fila de aprovações Human-in-the-Loop
    e auditoria imutável integrada.
    """

    def __init__(
        self,
        *,
        audit_log_path: str | Path | None = None,
        approval_ttl_seconds: float = DEFAULT_APPROVAL_TTL_SECONDS,
        custom_tool_tiers: dict[str, PolicyTier] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._audit = AuditLogger(log_path=audit_log_path)
        self._approval_ttl_seconds = max(1.0, float(approval_ttl_seconds))
        self._tool_tiers: dict[str, PolicyTier] = dict(_DEFAULT_TOOL_TIERS)
        if custom_tool_tiers:
            for name, tier in custom_tool_tiers.items():
                self._tool_tiers[name.strip().lower()] = PolicyTier(tier)
        self._approvals: dict[str, ApprovalRequest] = {}

    @property
    def audit_logger(self) -> AuditLogger:
        return self._audit

    def register_tool_tier(self, tool_name: str, tier: PolicyTier | int) -> None:
        with self._lock:
            self._tool_tiers[tool_name.strip().lower()] = PolicyTier(tier)

    def classify_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> PolicyTier:
        """Classifica uma ferramenta/ação em Tier 1, Tier 2 ou Tier 3."""
        name = (tool_name or "").strip().lower()
        if not name:
            return PolicyTier.TIER_3_CRITICAL

        # Inspeção dinâmica de argumentos para ferramentas polimórficas (ex.: gerenciar_arquivos)
        if args and isinstance(args, dict):
            action_val = str(
                args.get("acao") or args.get("action") or args.get("operacao") or args.get("mode") or ""
            ).strip().lower()
            if action_val in _DESTRUCTIVE_ARG_ACTIONS:
                return PolicyTier.TIER_3_CRITICAL
            if name == "gerenciar_arquivos" and action_val in _READONLY_ARG_ACTIONS:
                return PolicyTier.TIER_1_READ

            # Qualquer comando contendo flags destrutivas de shell ou URL webhook externa explícita
            if "webhook_url" in args and args.get("webhook_url"):
                return PolicyTier.TIER_3_CRITICAL

        with self._lock:
            if name in self._tool_tiers:
                return self._tool_tiers[name]

        if any(kw in name for kw in _TIER_3_KEYWORDS):
            return PolicyTier.TIER_3_CRITICAL

        if any(name.startswith(prefix) for prefix in _TIER_1_PREFIXES):
            return PolicyTier.TIER_1_READ

        # Padrão seguro para ferramentas desconhecidas de escrita/mutação
        return PolicyTier.TIER_2_MUTATION

    def _prune_expired_approvals_locked(self, now: float) -> None:
        for req in self._approvals.values():
            if req.status == "pending" and now >= req.expires_at:
                req.status = "expired"

    def request_approval(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        tier: PolicyTier | int = PolicyTier.TIER_3_CRITICAL,
        actor: str = "user",
        agent: str = "fryivs",
        correlation_id: str = "",
        reason: str = "",
        context_tainted: bool = False,
        ttl_seconds: float | None = None,
    ) -> ApprovalRequest:
        """Cria uma solicitação de aprovação Human-in-the-Loop pendente com UUID."""
        now = time.time()
        ttl = self._approval_ttl_seconds if ttl_seconds is None else max(0.01, float(ttl_seconds))
        req = ApprovalRequest(
            approval_id=str(uuid.uuid4()),
            tool=tool,
            tier=int(tier),
            args_summary=summarize_args(args),
            created_at=now,
            expires_at=now + ttl,
            status="pending",
            actor=actor,
            agent=agent,
            correlation_id=correlation_id or str(uuid.uuid4()),
            reason=reason or "Ação de alto impacto exige aprovação explícita humana.",
            context_tainted=context_tainted,
        )
        with self._lock:
            self._prune_expired_approvals_locked(now)
            self._approvals[req.approval_id] = req

        self._audit.log(
            actor=actor,
            agent=agent,
            tool=tool,
            tier=int(tier),
            correlation_id=req.correlation_id,
            status="pending_approval",
            details={
                "approval_id": req.approval_id,
                "context_tainted": context_tainted,
                "args_summary": req.args_summary,
                "reason": req.reason,
            },
        )
        return req

    def evaluate(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        context_tainted: bool = False,
        actor: str = "user",
        agent: str = "fryivs",
        correlation_id: str = "",
        approval_id: str | None = None,
        auto_create_approval: bool = True,
    ) -> PolicyDecision:
        """
        Avalia se `tool` pode ser executada diretamente ou exige aprovação Human-in-the-Loop.

        Regra de Taint-Tracking:
        Quando `context_tainted=True`, qualquer ação Tier 2 ou Tier 3 é elevada para
        `TIER_3_CRITICAL` e bloqueada até aprovação explícita.
        """
        corr_id = correlation_id or str(uuid.uuid4())
        base_tier = self.classify_tool(tool, args)
        effective_tier = base_tier
        taint_elevated = False

        if context_tainted and base_tier >= PolicyTier.TIER_2_MUTATION:
            effective_tier = PolicyTier.TIER_3_CRITICAL
            taint_elevated = True

        # Verifica aprovação explícita prévia (se approval_id foi fornecido)
        if approval_id:
            now = time.time()
            with self._lock:
                self._prune_expired_approvals_locked(now)
                existing = self._approvals.get(approval_id)
                if existing is not None:
                    if existing.status == "approved" and existing.tool == tool:
                        self._audit.log(
                            actor=actor,
                            agent=agent,
                            tool=tool,
                            tier=int(effective_tier),
                            correlation_id=corr_id,
                            status="allowed_by_approval",
                            details={
                                "approval_id": approval_id,
                                "context_tainted": context_tainted,
                                "args_summary": summarize_args(args),
                            },
                        )
                        return PolicyDecision(
                            allowed=True,
                            requires_approval=False,
                            tier=base_tier,
                            effective_tier=effective_tier,
                            taint_elevated=taint_elevated,
                            reason=f"Ação autorizada pela aprovação explícita {approval_id}.",
                            approval_request=existing,
                        )
                    if existing.status in ("denied", "expired"):
                        self._audit.log(
                            actor=actor,
                            agent=agent,
                            tool=tool,
                            tier=int(effective_tier),
                            correlation_id=corr_id,
                            status=f"blocked_{existing.status}",
                            details={"approval_id": approval_id},
                        )
                        return PolicyDecision(
                            allowed=False,
                            requires_approval=True,
                            tier=base_tier,
                            effective_tier=effective_tier,
                            taint_elevated=taint_elevated,
                            reason=f"Aprovação {approval_id} encontra-se '{existing.status}'.",
                            approval_request=existing,
                        )

        # Tier 1 ou Tier 2 limpo (sem taint) -> execução permitida com auditoria
        if effective_tier < PolicyTier.TIER_3_CRITICAL:
            reason = (
                "Ação Tier 1 (leitura/consulta) autorizada."
                if effective_tier == PolicyTier.TIER_1_READ
                else "Ação Tier 2 (mutação local reversível) autorizada com auditoria."
            )
            self._audit.log(
                actor=actor,
                agent=agent,
                tool=tool,
                tier=int(effective_tier),
                correlation_id=corr_id,
                status="allowed",
                details={
                    "context_tainted": context_tainted,
                    "args_summary": summarize_args(args),
                },
            )
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                tier=base_tier,
                effective_tier=effective_tier,
                taint_elevated=False,
                reason=reason,
            )

        # Tier 3 ou Tier 2 elevado por Taint-Tracking -> exige aprovação Human-in-the-Loop
        if taint_elevated:
            reason = (
                f"Taint-Tracking ativado: contexto contém dados externos não confiáveis; "
                f"ação '{tool}' (Tier {int(base_tier)}) elevada para aprovação explícita Tier 3."
            )
        else:
            reason = (
                f"Ação '{tool}' classificada como Tier 3 (irreversível/externa/crítica); "
                f"aprovação explícita Human-in-the-Loop obrigatória."
            )

        approval_req: ApprovalRequest | None = None
        if auto_create_approval:
            approval_req = self.request_approval(
                tool,
                args,
                tier=effective_tier,
                actor=actor,
                agent=agent,
                correlation_id=corr_id,
                reason=reason,
                context_tainted=context_tainted,
            )
        else:
            self._audit.log(
                actor=actor,
                agent=agent,
                tool=tool,
                tier=int(effective_tier),
                correlation_id=corr_id,
                status="requires_approval",
                details={"context_tainted": context_tainted, "reason": reason},
            )

        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            tier=base_tier,
            effective_tier=effective_tier,
            taint_elevated=taint_elevated,
            reason=reason,
            approval_request=approval_req,
        )

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        now = time.time()
        with self._lock:
            self._prune_expired_approvals_locked(now)
            return self._approvals.get(approval_id)

    def list_approvals(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        now = time.time()
        with self._lock:
            self._prune_expired_approvals_locked(now)
            items = list(self._approvals.values())
            if status is not None:
                items = [item for item in items if item.status == status]
            return sorted(items, key=lambda r: r.created_at, reverse=True)

    def resolve_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        decided_by: str = "user",
        note: str = "",
    ) -> ApprovalRequest:
        """Aprova ou nega uma solicitação pendente; recusa solicitações já expiradas ou decididas."""
        now = time.time()
        with self._lock:
            self._prune_expired_approvals_locked(now)
            req = self._approvals.get(approval_id)
            if req is None:
                raise KeyError(f"Aprovação '{approval_id}' não encontrada.")
            if req.status == "expired":
                raise ValueError(f"Aprovação '{approval_id}' expirou e não pode mais ser decidida.")
            if req.status != "pending":
                raise ValueError(
                    f"Aprovação '{approval_id}' já foi finalizada com status '{req.status}'."
                )

            req.status = "approved" if approved else "denied"
            req.decided_at = now
            req.decided_by = decided_by
            req.decision_note = str(redact_secrets(note))

        self._audit.log(
            actor=decided_by,
            agent=req.agent,
            tool=req.tool,
            tier=req.tier,
            correlation_id=req.correlation_id,
            status=req.status,
            details={
                "approval_id": req.approval_id,
                "decision_note": req.decision_note,
            },
        )
        return req

    def approve(self, approval_id: str, decided_by: str = "user", note: str = "") -> ApprovalRequest:
        return self.resolve_approval(approval_id, approved=True, decided_by=decided_by, note=note)

    def deny(self, approval_id: str, decided_by: str = "user", note: str = "") -> ApprovalRequest:
        return self.resolve_approval(approval_id, approved=False, decided_by=decided_by, note=note)

    def record_audit(
        self,
        *,
        actor: str,
        agent: str,
        tool: str,
        tier: int | PolicyTier,
        correlation_id: str,
        status: str,
        tokens: int = 0,
        duration_ms: float = 0.0,
        details: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        return self._audit.log(
            actor=actor,
            agent=agent,
            tool=tool,
            tier=tier,
            correlation_id=correlation_id,
            status=status,
            tokens=tokens,
            duration_ms=duration_ms,
            details=details,
        )


# =============================================================================
# Singleton Thread-Safe
# =============================================================================

_policy_singleton_lock = threading.Lock()
_policy_engine_instance: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    """Retorna a instância singleton global do PolicyEngine."""
    global _policy_engine_instance
    with _policy_singleton_lock:
        if _policy_engine_instance is None:
            _policy_engine_instance = PolicyEngine()
        return _policy_engine_instance


def reset_policy_engine(
    *,
    audit_log_path: str | Path | None = None,
    approval_ttl_seconds: float = DEFAULT_APPROVAL_TTL_SECONDS,
) -> PolicyEngine:
    """Recria o singleton global (utilitário para testes isolados)."""
    global _policy_engine_instance
    with _policy_singleton_lock:
        _policy_engine_instance = PolicyEngine(
            audit_log_path=audit_log_path,
            approval_ttl_seconds=approval_ttl_seconds,
        )
        return _policy_engine_instance
