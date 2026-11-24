"""
Ponte Corporativa n8n (HMAC-SHA256 + SSRF Guard + REST API + MCP Streamable HTTP + FastAPI Router)
para a assistente F.R.Y.I.Vs.

Implementa a Camada 4 do Plano de Super Evolução:
- Assinatura e validação HMAC-SHA256 com janela anti-replay de ±60s e cache de nonces
  (headers: X-Fryivs-Timestamp, X-Fryivs-Nonce, X-Fryivs-Signature, X-Fryivs-Correlation-Id).
- Proteção contra SSRF (`validar_url_externa`) bloqueando 169.254.0.0/16 (cloud metadata),
  redes privadas RFC1918/loopback/link-local/CGNAT e esquemas perigosos (file://, gopher://, etc.),
  permitindo apenas o host explícito de `N8N_BASE_URL` / allowlist ou hosts públicos `https://`.
- Cliente REST (`/api/v1/workflows`, `/api/v1/executions`) e cliente MCP Streamable HTTP / SSE.
- FastAPI `n8n_router` (`/api/n8n/status`, `/workflows`, `/trigger` protegidos por E2EE +
  `/api/n8n/callback` verificado criptograficamente via HMAC-SHA256).
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
import uuid
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

try:
    from core.e2ee_auth import require_e2ee_session as _require_e2ee_session
except ImportError:  # pragma: no cover
    def _require_e2ee_session() -> None:  # type: ignore[misc]
        return None


# =============================================================================
# Constantes de Protocolo & Segurança
# =============================================================================

HMAC_HEADER_SIGNATURE = "X-Fryivs-Signature"
HMAC_HEADER_TIMESTAMP = "X-Fryivs-Timestamp"
HMAC_HEADER_NONCE = "X-Fryivs-Nonce"
HMAC_HEADER_CORRELATION_ID = "X-Fryivs-Correlation-Id"

DEFAULT_HMAC_MAX_SKEW_SECONDS = 60
_SIGNATURE_PREFIX = "sha256="
_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

_METADATA_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
    "instance-data",
})

_BLOCKED_LOCAL_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
)

_BLOCKED_LOCAL_EXACT = frozenset({
    "localhost",
    "localhost.localdomain",
    "host.docker.internal",
    "gateway.docker.internal",
})

_LINK_LOCAL_V4 = ipaddress.ip_network("169.254.0.0/16")
_LINK_LOCAL_V6 = ipaddress.ip_network("fe80::/10")
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")


# =============================================================================
# Guardião SSRF (`validar_url_externa`)
# =============================================================================


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Tenta interpretar `host` como IP literal, incluindo formas ofuscadas (decimal/hex/octal)."""
    cleaned = host.strip().strip("[]")
    if not cleaned:
        return None
    try:
        return ipaddress.ip_address(cleaned)
    except ValueError:
        pass

    # Detecta IPs IPv4 ofuscados como 2130706433, 0x7f000001, 0177.0.0.1, 127.1
    if re.fullmatch(r"[0-9a-fA-FxX.]+", cleaned):
        try:
            packed = socket.inet_aton(cleaned)
            return ipaddress.IPv4Address(packed)
        except OSError:
            pass
    return None


def _is_cloud_metadata_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Identifica endereços link-local de metadados cloud (169.254.0.0/16, fe80::/10)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in _LINK_LOCAL_V4
    return ip in _LINK_LOCAL_V6


def _is_disallowed_non_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Retorna True se o IP não for roteável publicamente na internet."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_V4:
        return True
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    return 443 if scheme == "https" else 80


def _parse_allowlist_entries(
    allowlist_hosts: Iterable[str] | None,
) -> list[tuple[str, int | None]]:
    """
    Normaliza entradas da allowlist em pares `(hostname_lower, port_or_none)`.
    - URL completa (ex: `http://127.0.0.1:5678`) fixa host E porta efetiva.
    - `host:port` fixa host e porta.
    - `host` puro libera o host em qualquer porta.
    """
    raw_items: list[str] = []
    if allowlist_hosts:
        raw_items.extend(str(item).strip() for item in allowlist_hosts if str(item).strip())

    env_base = os.environ.get("N8N_BASE_URL", "").strip()
    if env_base:
        raw_items.append(env_base)

    env_extra = os.environ.get("N8N_ALLOWED_HOSTS", "").strip()
    if env_extra:
        raw_items.extend(part.strip() for part in env_extra.split(",") if part.strip())

    entries: list[tuple[str, int | None]] = []
    for item in raw_items:
        if "://" in item:
            parsed = urlparse(item)
            if parsed.hostname:
                host = parsed.hostname.lower().rstrip(".")
                port = _effective_port(parsed.scheme.lower(), parsed.port)
                entries.append((host, port))
        else:
            # Trata `[::1]:5678`, `127.0.0.1:5678`, `n8n.internal`
            probe = urlparse(f"http://{item}")
            if probe.hostname:
                host = probe.hostname.lower().rstrip(".")
                entries.append((host, probe.port))
    return entries


def _matches_allowlist(
    host: str,
    effective_port: int,
    allowlist: list[tuple[str, int | None]],
) -> bool:
    for allowed_host, allowed_port in allowlist:
        if host == allowed_host:
            if allowed_port is None or allowed_port == effective_port:
                return True
    return False


def validar_url_externa(
    url: str,
    allowlist_hosts: Iterable[str] | None = None,
    *,
    resolve_dns: bool = False,
) -> tuple[bool, str]:
    """
    Valida uma URL externa contra SSRF antes de qualquer requisição de saída.

    Regras:
    - Bloqueia esquemas não-HTTP(S) (`file://`, `gopher://`, `ftp://`, `data://`, etc.).
    - Bloqueia credenciais embutidas (`user:pass@host`) e caracteres de controle.
    - Bloqueia incondicionalmente endpoints de cloud metadata (`169.254.0.0/16`, `fe80::/10`,
      `metadata.google.internal`).
    - Permite explicitamente o host/porta de `N8N_BASE_URL` (e `allowlist_hosts` / `N8N_ALLOWED_HOSTS`),
      inclusive em `http://` local quando explicitamente autorizado.
    - Para qualquer outro destino, exige estritamente `https://` em host/IP público roteável,
      bloqueando `localhost`, `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
      `100.64.0.0/10`, `::1`, `fc00::/7`, IPv4-mapped IPv6 e IPs ofuscados.
    - Quando `resolve_dns=True`, valida também todos os IPs retornados via DNS contra endereços privados.

    Retorna:
        `(True, "OK")` (ou `"OK (allowlisted)"`) se segura; `(False, "<motivo>")` se bloqueada.
    """
    if not isinstance(url, str) or not url.strip():
        return False, "URL ausente ou vazia."

    cleaned = url.strip()
    if _CONTROL_CHARS_RE.search(cleaned) or any(ch.isspace() for ch in cleaned):
        return False, "URL contém espaços ou caracteres de controle inválidos."

    try:
        parsed = urlparse(cleaned)
    except ValueError as exc:
        return False, f"URL malformada: {exc}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Esquema '{scheme or 'vazio'}' não permitido (bloqueio SSRF)."

    if parsed.username is not None or parsed.password is not None:
        return False, "URL com credenciais embutidas (userinfo) não é permitida."

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        return False, "URL sem hostname válido."

    try:
        port = _effective_port(scheme, parsed.port)
    except ValueError:
        return False, "Porta inválida na URL."

    # 1. Bloqueio absoluto de Cloud Metadata (nunca permitido mesmo via allowlist)
    if hostname in _METADATA_HOSTNAMES:
        return False, f"Acesso bloqueado ao endpoint de metadados cloud '{hostname}'."

    ip_literal = _parse_ip_literal(hostname)
    if ip_literal is not None and _is_cloud_metadata_ip(ip_literal):
        return False, f"Acesso bloqueado à faixa link-local/metadata '{ip_literal}' (169.254.0.0/16)."

    # 2. Allowlist explícita (N8N_BASE_URL + allowlist_hosts + N8N_ALLOWED_HOSTS)
    allowlist = _parse_allowlist_entries(allowlist_hosts)
    if _matches_allowlist(hostname, port, allowlist):
        return True, "OK (allowlisted)"

    # 3. Fora da allowlist: apenas HTTPS em host público!
    if scheme != "https":
        return (
            False,
            f"Apenas HTTPS é permitido para hosts externos fora da allowlist (recebido '{scheme}://').",
        )

    if hostname in _BLOCKED_LOCAL_EXACT or any(hostname.endswith(sfx) for sfx in _BLOCKED_LOCAL_SUFFIXES):
        return False, f"Host interno/local '{hostname}' bloqueado por política SSRF."

    if ip_literal is not None:
        if _is_disallowed_non_public_ip(ip_literal):
            return False, f"IP privado/reservado '{ip_literal}' bloqueado por política SSRF."
        return True, "OK"

    # 4. Resolução DNS opcional (defesa contra DNS rebinding / localtest.me)
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError:
            infos = []
        for info in infos:
            addr_str = info[4][0]
            resolved_ip = _parse_ip_literal(addr_str)
            if resolved_ip is not None and (
                _is_cloud_metadata_ip(resolved_ip) or _is_disallowed_non_public_ip(resolved_ip)
            ):
                return (
                    False,
                    f"Hostname '{hostname}' resolveu para endereço privado/bloqueado ({resolved_ip}).",
                )

    return True, "OK"


# =============================================================================
# Assinatura e Verificação HMAC-SHA256 (Anti-Replay ±60s)
# =============================================================================


def _canonical_body_bytes(raw_body: str | bytes) -> bytes:
    if isinstance(raw_body, bytes):
        return raw_body
    return raw_body.encode("utf-8")


def compute_hmac_signature(raw_body: str | bytes, timestamp: str | int, secret: str) -> str:
    """Computa `sha256=<hex>` sobre `<timestamp>.<raw_body>` (bytes exatos UTF-8)."""
    if not secret:
        raise ValueError("Segredo HMAC não pode ser vazio.")
    canonical = f"{timestamp}.".encode("utf-8") + _canonical_body_bytes(raw_body)
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


def sign_webhook_payload(
    raw_body: str | bytes,
    secret: str,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str]:
    """
    Gera headers HTTP assinados com HMAC-SHA256 compatíveis com o hub n8n F.R.Y.I.Vs:
    - `X-Fryivs-Timestamp`: epoch segundos (int)
    - `X-Fryivs-Nonce`: token aleatório único (hex 32 chars)
    - `X-Fryivs-Signature`: `sha256=<hmac_hex>` sobre `<timestamp>.<raw_body>`
    - `X-Fryivs-Correlation-Id`: UUID de rastreio distribuído
    """
    if not secret or not secret.strip():
        raise ValueError("N8N_HMAC_SECRET ausente para assinatura HMAC-SHA256.")

    ts = int(time.time()) if timestamp is None else int(timestamp)
    nonce_val = nonce or secrets.token_hex(16)
    corr_val = correlation_id or f"fryivs-{uuid.uuid4().hex[:16]}"
    sig = compute_hmac_signature(raw_body, ts, secret.strip())

    return {
        "Content-Type": "application/json",
        HMAC_HEADER_TIMESTAMP: str(ts),
        HMAC_HEADER_NONCE: nonce_val,
        HMAC_HEADER_SIGNATURE: sig,
        HMAC_HEADER_CORRELATION_ID: corr_val,
    }


def verify_webhook_signature(
    raw_body: str | bytes,
    timestamp: str | int | None,
    signature: str | None,
    secret: str | None,
    *,
    nonce: str | None = None,
    max_skew_seconds: int = DEFAULT_HMAC_MAX_SKEW_SECONDS,
    now: float | None = None,
    nonce_cache: dict[str, float] | None = None,
) -> tuple[bool, str]:
    """
    Verifica assinatura HMAC-SHA256, janela de replay (±60s) e unicidade de nonce.
    Usa `hmac.compare_digest` (tempo constante).
    """
    if not secret or not secret.strip():
        return False, "N8N_HMAC_SECRET não configurado no servidor."

    if timestamp is None or str(timestamp).strip() == "":
        return False, f"Header '{HMAC_HEADER_TIMESTAMP}' ausente."

    if not signature or not isinstance(signature, str):
        return False, f"Header '{HMAC_HEADER_SIGNATURE}' ausente."

    try:
        ts_val = float(str(timestamp).strip())
    except ValueError:
        return False, f"Header '{HMAC_HEADER_TIMESTAMP}' inválido (esperado epoch em segundos)."

    current_time = time.time() if now is None else float(now)
    skew = abs(current_time - ts_val)
    if skew > max_skew_seconds:
        return (
            False,
            f"Timestamp fora da janela anti-replay (±{max_skew_seconds}s; desvio={int(skew)}s).",
        )

    sig_clean = signature.strip().lower()
    if not sig_clean.startswith(_SIGNATURE_PREFIX):
        return False, "Formato de assinatura inválido (esperado 'sha256=<hex>')."

    hex_part = sig_clean[len(_SIGNATURE_PREFIX):]
    if not _HEX_64_RE.fullmatch(hex_part):
        return False, "Assinatura HMAC malformada (hex SHA-256 inválido)."

    expected = compute_hmac_signature(raw_body, str(timestamp).strip(), secret.strip())
    if not hmac.compare_digest(expected.encode("utf-8"), sig_clean.encode("utf-8")):
        return False, "Assinatura HMAC-SHA256 inválida."

    # Anti-replay de assinatura + nonce dentro da janela (impede replay mesmo se X-Fryivs-Nonce for removido/alterado)
    if nonce_cache is not None:
        expiry_cutoff = current_time - max(max_skew_seconds * 2, 120)
        stale_keys = [k for k, seen_at in nonce_cache.items() if seen_at < expiry_cutoff]
        for k in stale_keys:
            nonce_cache.pop(k, None)

        sig_key = f"sig:{str(timestamp).strip()}:{hex_part}"
        if sig_key in nonce_cache:
            return False, "Requisição já processada (tentativa de replay da assinatura bloqueada)."

        nonce_clean = nonce.strip() if isinstance(nonce, str) and nonce.strip() else ""
        nonce_key = f"nonce:{nonce_clean}" if nonce_clean else ""
        if nonce_key and nonce_key in nonce_cache:
            return False, "Nonce já utilizado (tentativa de replay bloqueada)."

        nonce_cache[sig_key] = current_time
        if nonce_key:
            nonce_cache[nonce_key] = current_time

    return True, "OK"


# =============================================================================
# Singleton N8nBridge (Webhooks HMAC + REST API + MCP Streamable HTTP)
# =============================================================================


class N8nBridge:
    """
    Ponte corporativa thread-safe entre F.R.Y.I.Vs e n8n (Cloud ou Self-Hosted Docker).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        hmac_secret: str | None = None,
        webhook_url: str | None = None,
        mcp_url: str | None = None,
        mcp_token: str | None = None,
        max_callbacks: int = 100,
    ) -> None:
        self._override_base_url = base_url
        self._override_api_key = api_key
        self._override_hmac_secret = hmac_secret
        self._override_webhook_url = webhook_url
        self._override_mcp_url = mcp_url
        self._override_mcp_token = mcp_token

        self._lock = threading.RLock()
        self._seen_nonces: dict[str, float] = {}
        self._callbacks: collections.deque[dict[str, Any]] = collections.deque(maxlen=max_callbacks)
        self._callback_handlers: list[Callable[[dict[str, Any]], None]] = []

    @property
    def base_url(self) -> str:
        val = self._override_base_url if self._override_base_url is not None else os.environ.get("N8N_BASE_URL", "")
        return val.strip().rstrip("/")

    @property
    def api_key(self) -> str:
        val = self._override_api_key if self._override_api_key is not None else os.environ.get("N8N_API_KEY", "")
        return val.strip()

    @property
    def hmac_secret(self) -> str:
        val = (
            self._override_hmac_secret
            if self._override_hmac_secret is not None
            else os.environ.get("N8N_HMAC_SECRET", "")
        )
        return val.strip()

    @property
    def webhook_url(self) -> str:
        if self._override_webhook_url is not None:
            return self._override_webhook_url.strip()
        env_wh = os.environ.get("N8N_WEBHOOK_URL", "").strip()
        if env_wh:
            return env_wh
        if self.base_url:
            return f"{self.base_url}/webhook/fryivs-hub"
        return ""

    @property
    def mcp_url(self) -> str:
        if self._override_mcp_url is not None:
            return self._override_mcp_url.strip()
        env_mcp = os.environ.get("N8N_MCP_URL", "").strip()
        if env_mcp:
            return env_mcp
        if self.base_url:
            return f"{self.base_url}/mcp-server/http"
        return ""

    @property
    def mcp_token(self) -> str:
        if self._override_mcp_token is not None:
            return self._override_mcp_token.strip()
        return os.environ.get("N8N_MCP_TOKEN", "").strip() or self.api_key

    @property
    def max_skew_seconds(self) -> int:
        try:
            return max(5, int(os.environ.get("N8N_HMAC_MAX_SKEW_SECONDS", str(DEFAULT_HMAC_MAX_SKEW_SECONDS))))
        except ValueError:
            return DEFAULT_HMAC_MAX_SKEW_SECONDS

    def _effective_allowlist(self) -> list[str]:
        hosts: list[str] = []
        if self.base_url:
            hosts.append(self.base_url)
        if self.mcp_url:
            parsed_mcp = urlparse(self.mcp_url)
            if parsed_mcp.scheme and parsed_mcp.netloc:
                hosts.append(f"{parsed_mcp.scheme}://{parsed_mcp.netloc}")
        return hosts

    def _should_resolve_dns(self) -> bool:
        return not bool(os.environ.get("PYTEST_CURRENT_TEST"))

    # ------------------------------------------------------------------
    # HMAC Helpers
    # ------------------------------------------------------------------

    def build_hmac_headers(
        self,
        raw_body: str | bytes,
        *,
        secret: str | None = None,
        timestamp: int | None = None,
        nonce: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, str]:
        effective_secret = (secret if secret is not None else self.hmac_secret).strip()
        return sign_webhook_payload(
            raw_body,
            effective_secret,
            timestamp=timestamp,
            nonce=nonce,
            correlation_id=correlation_id,
        )

    def verify_hmac_request(
        self,
        raw_body: str | bytes,
        timestamp: str | int | None,
        signature: str | None,
        *,
        nonce: str | None = None,
        secret: str | None = None,
        max_skew_seconds: int | None = None,
        now: float | None = None,
        check_replay: bool = True,
    ) -> tuple[bool, str]:
        effective_secret = (secret if secret is not None else self.hmac_secret).strip()
        skew = self.max_skew_seconds if max_skew_seconds is None else max_skew_seconds
        with self._lock:
            cache = self._seen_nonces if check_replay else None
            return verify_webhook_signature(
                raw_body,
                timestamp,
                signature,
                effective_secret,
                nonce=nonce,
                max_skew_seconds=skew,
                now=now,
                nonce_cache=cache,
            )

    def clear_nonce_cache(self) -> None:
        with self._lock:
            self._seen_nonces.clear()

    # ------------------------------------------------------------------
    # Webhook Dispatch (Assinado HMAC-SHA256 + SSRF Guard)
    # ------------------------------------------------------------------

    def trigger_webhook(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        webhook_url: str | None = None,
        correlation_id: str | None = None,
        timeout: float = 15.0,
        require_hmac: bool = False,
    ) -> dict[str, Any]:
        """
        Dispara webhook corporativo n8n com proteção SSRF e headers HMAC-SHA256.
        Serializa exatamente uma vez o JSON e envia os bytes assinados em `data=...`.
        """
        if requests is None:
            return {"ok": False, "status_code": 0, "error": "Biblioteca 'requests' não disponível."}

        target_url = (webhook_url or "").strip() or self.webhook_url
        if not target_url:
            return {
                "ok": False,
                "status_code": 0,
                "error": "Nenhuma URL de webhook n8n configurada (defina N8N_BASE_URL ou N8N_WEBHOOK_URL).",
            }

        # Permite caminho relativo de webhook (ex: "fryivs-hub") se N8N_BASE_URL estiver definido
        if "://" not in target_url and ":" not in target_url and self.base_url:
            clean_path = target_url.lstrip("/")
            if ".." in clean_path.split("/"):
                return {"ok": False, "status_code": 0, "error": "URL bloqueada por SSRF: path traversal inválido."}
            if not clean_path.startswith("webhook"):
                clean_path = f"webhook/{clean_path}"
            target_url = f"{self.base_url}/{clean_path}"

        ok_url, reason = validar_url_externa(
            target_url,
            allowlist_hosts=self._effective_allowlist(),
            resolve_dns=self._should_resolve_dns(),
        )
        if not ok_url:
            return {"ok": False, "status_code": 0, "error": f"URL bloqueada por SSRF: {reason}"}

        corr_id = correlation_id or f"fryivs-{uuid.uuid4().hex[:16]}"
        body_obj: dict[str, Any] = {
            "action": action.strip() or "custom",
            "correlation_id": corr_id,
            "source": "F.R.Y.I.Vs",
            "payload": payload if isinstance(payload, dict) else ({} if payload is None else {"data": payload}),
        }
        raw_body = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))

        if self.hmac_secret:
            headers = self.build_hmac_headers(raw_body, correlation_id=corr_id)
        elif require_hmac:
            return {
                "ok": False,
                "status_code": 0,
                "correlation_id": corr_id,
                "error": "N8N_HMAC_SECRET obrigatório não configurado.",
            }
        else:
            headers = {
                "Content-Type": "application/json",
                HMAC_HEADER_TIMESTAMP: str(int(time.time())),
                HMAC_HEADER_NONCE: secrets.token_hex(16),
                HMAC_HEADER_CORRELATION_ID: corr_id,
            }

        try:
            resp = requests.post(
                target_url,
                data=raw_body.encode("utf-8"),
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
            try:
                resp_data: Any = resp.json()
            except ValueError:
                resp_data = resp.text[:500]

            return {
                "ok": 200 <= resp.status_code < 300,
                "status_code": resp.status_code,
                "correlation_id": corr_id,
                "signed": bool(self.hmac_secret),
                "data": resp_data,
                "error": None if 200 <= resp.status_code < 300 else f"HTTP {resp.status_code}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "status_code": 0,
                "correlation_id": corr_id,
                "signed": bool(self.hmac_secret),
                "error": f"Erro ao chamar webhook n8n: {exc}",
            }

    # ------------------------------------------------------------------
    # REST API v1 (/api/v1/workflows e /api/v1/executions)
    # ------------------------------------------------------------------

    def _rest_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-N8N-API-KEY": self.api_key,
        }

    def list_workflows(
        self,
        *,
        active_only: bool = False,
        tag: str | None = None,
        limit: int = 50,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Lista workflows na instância n8n via `GET /api/v1/workflows`."""
        if requests is None:
            return {"ok": False, "workflows": [], "error": "Biblioteca 'requests' não disponível."}
        if not self.base_url:
            return {"ok": False, "workflows": [], "error": "N8N_BASE_URL não configurado."}
        if not self.api_key:
            return {"ok": False, "workflows": [], "error": "N8N_API_KEY não configurado."}

        endpoint = f"{self.base_url}/api/v1/workflows"
        ok_url, reason = validar_url_externa(
            endpoint,
            allowlist_hosts=self._effective_allowlist(),
            resolve_dns=self._should_resolve_dns(),
        )
        if not ok_url:
            return {"ok": False, "workflows": [], "error": f"URL bloqueada por SSRF: {reason}"}

        params: dict[str, Any] = {"limit": max(1, min(int(limit), 250))}
        if active_only:
            params["active"] = "true"
        if tag and tag.strip():
            params["tags"] = tag.strip()

        try:
            resp = requests.get(
                endpoint,
                headers=self._rest_headers(),
                params=params,
                timeout=timeout,
                allow_redirects=False,
            )
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "workflows": [],
                    "error": f"n8n API retornou HTTP {resp.status_code}: {resp.text[:200]}",
                }
            payload = resp.json()
            raw_items = payload.get("data", payload) if isinstance(payload, dict) else payload
            workflows = []
            for wf in raw_items if isinstance(raw_items, list) else []:
                raw_tags = wf.get("tags") or []
                tag_names = [
                    t.get("name", str(t)) if isinstance(t, dict) else str(t)
                    for t in raw_tags
                ]
                workflows.append(
                    {
                        "id": str(wf.get("id", "")),
                        "name": str(wf.get("name", "Sem nome")),
                        "active": bool(wf.get("active", False)),
                        "tags": tag_names,
                        "updatedAt": wf.get("updatedAt"),
                    }
                )
            return {
                "ok": True,
                "status_code": 200,
                "count": len(workflows),
                "workflows": workflows,
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "status_code": 0, "workflows": [], "error": f"Erro ao consultar n8n: {exc}"}

    def list_executions(
        self,
        *,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Consulta execuções recentes na instância n8n via `GET /api/v1/executions`."""
        if requests is None:
            return {"ok": False, "executions": [], "error": "Biblioteca 'requests' não disponível."}
        if not self.base_url:
            return {"ok": False, "executions": [], "error": "N8N_BASE_URL não configurado."}
        if not self.api_key:
            return {"ok": False, "executions": [], "error": "N8N_API_KEY não configurado."}

        endpoint = f"{self.base_url}/api/v1/executions"
        ok_url, reason = validar_url_externa(
            endpoint,
            allowlist_hosts=self._effective_allowlist(),
            resolve_dns=self._should_resolve_dns(),
        )
        if not ok_url:
            return {"ok": False, "executions": [], "error": f"URL bloqueada por SSRF: {reason}"}

        params: dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
        if workflow_id and workflow_id.strip():
            params["workflowId"] = workflow_id.strip()
        if status and status.strip():
            params["status"] = status.strip()

        try:
            resp = requests.get(
                endpoint,
                headers=self._rest_headers(),
                params=params,
                timeout=timeout,
                allow_redirects=False,
            )
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "executions": [],
                    "error": f"n8n API retornou HTTP {resp.status_code}: {resp.text[:200]}",
                }
            payload = resp.json()
            raw_items = payload.get("data", payload) if isinstance(payload, dict) else payload
            executions = []
            for ex in raw_items if isinstance(raw_items, list) else []:
                executions.append(
                    {
                        "id": str(ex.get("id", "")),
                        "workflowId": str(ex.get("workflowId", "")),
                        "status": str(ex.get("status", "unknown")),
                        "mode": str(ex.get("mode", "")),
                        "startedAt": ex.get("startedAt"),
                        "stoppedAt": ex.get("stoppedAt"),
                    }
                )
            return {
                "ok": True,
                "status_code": 200,
                "count": len(executions),
                "executions": executions,
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "status_code": 0, "executions": [], "error": f"Erro ao consultar execuções: {exc}"}

    # ------------------------------------------------------------------
    # MCP Streamable HTTP / SSE Bridge Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_mcp_response(resp: Any) -> dict[str, Any]:
        """Suporta tanto `application/json` quanto `text/event-stream` (Streamable HTTP MCP)."""
        content_type = str(resp.headers.get("Content-Type", "")).lower()
        if "text/event-stream" in content_type:
            last_obj: dict[str, Any] | None = None
            for line in resp.text.splitlines():
                line_s = line.strip()
                if line_s.startswith("data:"):
                    raw_chunk = line_s[5:].strip()
                    if not raw_chunk or raw_chunk == "[DONE]":
                        continue
                    try:
                        parsed = json.loads(raw_chunk)
                        if isinstance(parsed, dict):
                            last_obj = parsed
                    except json.JSONDecodeError:
                        continue
            if last_obj is not None:
                return last_obj
            return {"error": {"message": "Resposta SSE MCP sem frame JSON válido."}}
        return resp.json()

    def mcp_rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        mcp_url: str | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Executa uma chamada JSON-RPC 2.0 sobre MCP Streamable HTTP contra o n8n."""
        if requests is None:
            return {"ok": False, "error": "Biblioteca 'requests' não disponível."}

        target = (mcp_url or "").strip() or self.mcp_url
        if not target:
            return {"ok": False, "error": "N8N_MCP_URL (ou N8N_BASE_URL) não configurado."}

        ok_url, reason = validar_url_externa(
            target,
            allowlist_hosts=self._effective_allowlist(),
            resolve_dns=self._should_resolve_dns(),
        )
        if not ok_url:
            return {"ok": False, "error": f"MCP URL bloqueada por SSRF: {reason}"}

        req_id = f"fryivs-mcp-{uuid.uuid4().hex[:12]}"
        rpc_body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.mcp_token:
            headers["Authorization"] = f"Bearer {self.mcp_token}"

        try:
            resp = requests.post(
                target,
                json=rpc_body,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
            if resp.status_code not in (200, 202):
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": f"MCP HTTP {resp.status_code}: {resp.text[:200]}",
                }
            data = self._parse_mcp_response(resp)
            if "error" in data and data["error"]:
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": data["error"],
                }
            return {
                "ok": True,
                "status_code": resp.status_code,
                "result": data.get("result"),
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "status_code": 0, "error": f"Erro na chamada MCP n8n: {exc}"}

    def mcp_list_tools(self, *, mcp_url: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
        """Lista ferramentas MCP expostas pelo MCP Server Trigger do n8n."""
        res = self.mcp_rpc("tools/list", {}, mcp_url=mcp_url, timeout=timeout)
        if not res.get("ok"):
            return {"ok": False, "tools": [], "error": res.get("error")}
        result = res.get("result") or {}
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return {"ok": True, "tools": tools, "count": len(tools), "error": None}

    def mcp_call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        mcp_url: str | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Invoca uma ferramenta MCP no n8n via JSON-RPC `tools/call`."""
        return self.mcp_rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
            mcp_url=mcp_url,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Callbacks Recebidos do n8n & Status
    # ------------------------------------------------------------------

    def register_callback_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            if handler not in self._callback_handlers:
                self._callback_handlers.append(handler)

    def record_callback(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._callbacks.append(event)
            handlers = list(self._callback_handlers)
        for cb in handlers:
            try:
                cb(event)
            except Exception:
                pass

    def get_recent_callbacks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._callbacks)
        return items[-max(1, limit):]

    def status(self) -> dict[str, Any]:
        """Retorna resumo seguro da ponte n8n (nunca expõe chaves/segredos)."""
        with self._lock:
            cb_count = len(self._callbacks)
        return {
            "configured": bool(self.base_url or self.webhook_url),
            "base_url": self.base_url or None,
            "webhook_url": self.webhook_url or None,
            "mcp_url": self.mcp_url or None,
            "has_api_key": bool(self.api_key),
            "has_hmac_secret": bool(self.hmac_secret),
            "max_skew_seconds": self.max_skew_seconds,
            "recent_callbacks_count": cb_count,
        }


# Singleton global thread-safe
_bridge_lock = threading.Lock()
_bridge_instance: N8nBridge | None = None


def get_n8n_bridge() -> N8nBridge:
    """Retorna a instância singleton thread-safe do `N8nBridge`."""
    global _bridge_instance
    if _bridge_instance is None:
        with _bridge_lock:
            if _bridge_instance is None:
                _bridge_instance = N8nBridge()
    return _bridge_instance


def reset_n8n_bridge() -> None:
    """Reinicia o singleton global (utilitário para testes isolados)."""
    global _bridge_instance
    with _bridge_lock:
        _bridge_instance = None


# =============================================================================
# FastAPI Router: /api/n8n/*
# =============================================================================


class N8nTriggerRequest(BaseModel):
    action: str = Field(
        default="custom",
        min_length=1,
        max_length=64,
        description="Ação do hub n8n ('briefing', 'alert', 'status', 'custom').",
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Dados estruturados da automação.")
    webhook_url: str | None = Field(default=None, description="URL ou path de webhook opcional.")
    correlation_id: str | None = Field(default=None, description="Correlation ID opcional para rastreamento.")


n8n_router = APIRouter(prefix="/api/n8n", tags=["n8n Integration"])


@n8n_router.get("/status")
def get_n8n_status(_e2ee: Any = Depends(_require_e2ee_session)) -> dict[str, Any]:
    """Retorna estado de configuração e saúde da ponte corporativa n8n."""
    return get_n8n_bridge().status()


@n8n_router.get("/workflows")
def get_n8n_workflows(
    active_only: bool = Query(default=False),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=250),
    _e2ee: Any = Depends(_require_e2ee_session),
) -> dict[str, Any]:
    """Lista workflows da instância n8n configurada via REST API v1."""
    return get_n8n_bridge().list_workflows(active_only=active_only, tag=tag, limit=limit)


@n8n_router.post("/trigger")
def post_n8n_trigger(
    req: N8nTriggerRequest,
    _e2ee: Any = Depends(_require_e2ee_session),
) -> dict[str, Any]:
    """Dispara um webhook n8n assinado com HMAC-SHA256 e proteção SSRF."""
    res = get_n8n_bridge().trigger_webhook(
        action=req.action,
        payload=req.payload,
        webhook_url=req.webhook_url,
        correlation_id=req.correlation_id,
    )
    if not res.get("ok") and str(res.get("error", "")).startswith("URL bloqueada por SSRF"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@n8n_router.post("/callback")
async def post_n8n_callback(
    request: Request,
    x_fryivs_timestamp: str = Header(default="", alias=HMAC_HEADER_TIMESTAMP),
    x_fryivs_signature: str = Header(default="", alias=HMAC_HEADER_SIGNATURE),
    x_fryivs_nonce: str = Header(default="", alias=HMAC_HEADER_NONCE),
    x_fryivs_correlation_id: str = Header(default="", alias=HMAC_HEADER_CORRELATION_ID),
) -> dict[str, Any]:
    """
    Recebe callbacks assíncronos do n8n autenticados via HMAC-SHA256 + anti-replay (±60s).
    Rejeita com HTTP 401 qualquer chamada sem assinatura válida, expirada ou replayed.
    """
    raw_body = await request.body()
    bridge = get_n8n_bridge()
    valid, reason = bridge.verify_hmac_request(
        raw_body=raw_body,
        timestamp=x_fryivs_timestamp,
        signature=x_fryivs_signature,
        nonce=x_fryivs_nonce or None,
    )
    if not valid:
        raise HTTPException(status_code=401, detail=f"Autenticação HMAC n8n falhou: {reason}")

    try:
        data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Corpo JSON inválido no callback n8n: {exc}") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Payload do callback n8n deve ser um objeto JSON.")

    corr_id = (
        x_fryivs_correlation_id.strip()
        or str(data.get("correlation_id", "")).strip()
        or f"n8n-cb-{uuid.uuid4().hex[:12]}"
    )
    event = {
        "correlation_id": corr_id,
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": data.get("action", "callback"),
        "status": data.get("status", "ok"),
        "data": data,
    }
    bridge.record_callback(event)
    return {
        "status": "accepted",
        "correlation_id": corr_id,
        "received_at": event["received_at"],
    }
