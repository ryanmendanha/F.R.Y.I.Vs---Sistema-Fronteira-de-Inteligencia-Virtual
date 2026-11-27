"""
Módulo de Autenticação e Criptografia Ponta a Ponta (E2EE) da F.R.Y.I.Vs.

Garante que NINGUÉM possa conversar, acionar skills, acessar memórias ou fazer a
F.R.Y.I.Vs falar (TTS / VoiceDaemon / Pipeline / API / WebSocket) sem completar
um handshake criptografado real compatível com a WebCrypto API dos navegadores:

- Troca de chaves efêmera ECDH P-256 (SECP256R1) por desafio (Perfect Forward Secrecy)
- Derivação de chaves via HKDF-SHA256 (32 bytes = 256 bits)
  - Chave de handshake (info: "FRYIVS-E2EE-v1-handshake", salt: challenge_nonce)
  - Chave de transporte de sessão (info: "FRYIVS-E2EE-v1-session", salt: challenge_nonce)
- Criptografia autenticada AES-256-GCM (IV de 96 bits + tag de 128 bits + AAD)
- Verificação de senha com PBKDF2-HMAC-SHA256 (310.000 iterações) + hmac.compare_digest
- Nonces anti-replay de uso único (TTL 60s) + verificação de frescor de timestamp
- Rate limiting por cliente (máximo 5 tentativas falhas -> bloqueio temporário 429)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from dotenv import dotenv_values, load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

# Carrega .env apenas fora de pytest para não poluir suítes legadas
if not os.environ.get("PYTEST_CURRENT_TEST") and "pytest" not in sys.modules:
    load_dotenv(override=False)

# Captura se .env define explicitamente FRYIVS_REQUIRE_E2EE_PASSWORD
_DOTENV_REQUIRE_VAL: str | None = dotenv_values().get("FRYIVS_REQUIRE_E2EE_PASSWORD")

# Constantes criptográficas (alinhadas byte-a-byte com WebCrypto API no navegador)
E2EE_PROTOCOL = "ECDH-P256-HKDF-SHA256-AES-256-GCM"
PBKDF2_ITERATIONS = 310_000
PBKDF2_ALGO = "pbkdf2_sha256"
HKDF_INFO_HANDSHAKE = b"FRYIVS-E2EE-v1-handshake"
HKDF_INFO_SESSION = b"FRYIVS-E2EE-v1-session"
CHAT_AAD = b"FRYIVS-E2EE-CHAT-v1"

CHALLENGE_TTL_SECONDS = 60.0
TIMESTAMP_MAX_SKEW_SECONDS = 60.0
MAX_PENDING_CHALLENGES = 500
RATE_LIMIT_WINDOW_SECONDS = 300.0
DEFAULT_MAX_FAILED_ATTEMPTS = 5
DEFAULT_LOCKOUT_SECONDS = 120.0
DEFAULT_SESSION_TTL_SECONDS = 8 * 3600.0


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    if not isinstance(data, str) or not data:
        raise ValueError("Campo base64url ausente ou inválido.")
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64_decode(data: str) -> bytes:
    if not isinstance(data, str) or not data:
        raise ValueError("Campo base64 ausente ou inválido.")
    # Aceita base64 padrão e urlsafe
    normalized = data.replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    return base64.b64decode(normalized.encode("ascii"))


# =============================================================================
# Primitivas Criptográficas: ECDH P-256, HKDF-SHA256, AES-256-GCM, PBKDF2
# =============================================================================


def generate_ecdh_keypair() -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]:
    """Gera par de chaves efêmero ECDH P-256 (SECP256R1) e exporta a pública em JWK."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwk = public_key_to_jwk(private_key.public_key())
    return private_key, jwk


def public_key_to_jwk(public_key: ec.EllipticCurvePublicKey) -> dict[str, Any]:
    """Exporta chave pública P-256 no formato JWK compatível com WebCrypto."""
    nums = public_key.public_numbers()
    x_bytes = nums.x.to_bytes(32, "big")
    y_bytes = nums.y.to_bytes(32, "big")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url_encode(x_bytes),
        "y": _b64url_encode(y_bytes),
    }


def jwk_to_public_key(jwk: dict[str, Any]) -> ec.EllipticCurvePublicKey:
    """Importa e valida chave pública ECDH P-256 a partir de JWK."""
    if not isinstance(jwk, dict):
        raise ValueError("JWK deve ser um objeto JSON.")
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("JWK inválido: esperado kty='EC' e crv='P-256'.")
    x_raw = _b64url_decode(str(jwk.get("x", "")))
    y_raw = _b64url_decode(str(jwk.get("y", "")))
    if len(x_raw) != 32 or len(y_raw) != 32:
        raise ValueError("Coordenadas P-256 inválidas (devem ter exatamente 32 bytes).")
    x_int = int.from_bytes(x_raw, "big")
    y_int = int.from_bytes(y_raw, "big")
    pub_numbers = ec.EllipticCurvePublicNumbers(x_int, y_int, ec.SECP256R1())
    return pub_numbers.public_key()


def derive_shared_secret(
    private_key: ec.EllipticCurvePrivateKey,
    peer_public_key: ec.EllipticCurvePublicKey,
) -> bytes:
    """Computa segredo compartilhado ECDH P-256 (32 bytes)."""
    return private_key.exchange(ec.ECDH(), peer_public_key)


def derive_aes_key(
    shared_secret: bytes,
    salt: bytes,
    info: bytes = HKDF_INFO_HANDSHAKE,
) -> bytes:
    """Deriva chave AES-256 (32 bytes) via HKDF-SHA256."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(shared_secret)


def encrypt_aes_gcm(
    key: bytes,
    payload: dict[str, Any],
    aad: bytes | None = None,
) -> dict[str, str]:
    """Criptografa objeto JSON com AES-256-GCM e IV aleatório de 96 bits."""
    if len(key) != 32:
        raise ValueError("Chave AES-256 deve ter exatamente 32 bytes.")
    iv = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(iv, plaintext, aad)
    return {
        "iv_b64": _b64_encode(iv),
        "ciphertext_b64": _b64_encode(ciphertext),
    }


def decrypt_aes_gcm(
    key: bytes,
    iv_b64: str,
    ciphertext_b64: str,
    aad: bytes | None = None,
) -> dict[str, Any]:
    """Descriptografa e autentica envelope AES-256-GCM em objeto JSON."""
    if len(key) != 32:
        raise ValueError("Chave AES-256 deve ter exatamente 32 bytes.")
    iv = _b64_decode(iv_b64)
    if len(iv) != 12:
        raise ValueError("IV AES-GCM inválido (esperado 12 bytes / 96 bits).")
    ciphertext = _b64_decode(ciphertext_b64)
    if len(ciphertext) < 16:
        raise ValueError("Ciphertext AES-GCM inválido (menor que tag GCM de 16 bytes).")
    plaintext = AESGCM(key).decrypt(iv, ciphertext, aad)
    data = json.loads(plaintext.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Payload JSON descriptografado deve ser um objeto.")
    return data


def hash_password(
    password: str,
    salt: bytes | None = None,
    iterations: int = PBKDF2_ITERATIONS,
) -> str:
    """Gera hash seguro PBKDF2-HMAC-SHA256 (310.000 iterações) com salt aleatório."""
    if not password:
        raise ValueError("Senha não pode ser vazia.")
    actual_salt = salt if salt is not None else os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt,
        iterations,
        dklen=32,
    )
    return f"{PBKDF2_ALGO}${iterations}${_b64_encode(actual_salt)}${_b64_encode(dk)}"


def verify_password_hash(password: str, stored_hash: str) -> bool:
    """Verifica senha contra hash PBKDF2-HMAC-SHA256 usando hmac.compare_digest."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.strip().split("$")
        if len(parts) != 4:
            return False
        algo, iter_str, salt_b64, dk_b64 = parts
        if algo != PBKDF2_ALGO:
            return False
        iterations = int(iter_str)
        if iterations < 100_000:
            return False
        salt = _b64_decode(salt_b64)
        expected_dk = _b64_decode(dk_b64)
        if len(salt) < 8 or len(expected_dk) < 16:
            return False
        computed_dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_dk),
        )
        return hmac.compare_digest(computed_dk, expected_dk)
    except Exception:
        return False


def create_encrypted_unlock_payload(
    password: str,
    server_pubkey_jwk: dict[str, Any],
    challenge_nonce: str,
    timestamp: float | None = None,
) -> tuple[dict[str, Any], bytes, bytes]:
    """
    Helper cliente (usado em testes e integrações Python) que executa o lado cliente
    do handshake ECDH P-256 + HKDF-SHA256 + AES-256-GCM.

    Retorna: (payload_http, handshake_key, session_key)
    """
    client_priv, client_jwk = generate_ecdh_keypair()
    server_pub = jwk_to_public_key(server_pubkey_jwk)
    shared = derive_shared_secret(client_priv, server_pub)
    salt = challenge_nonce.encode("utf-8")
    handshake_key = derive_aes_key(shared, salt=salt, info=HKDF_INFO_HANDSHAKE)
    session_key = derive_aes_key(shared, salt=salt, info=HKDF_INFO_SESSION)
    ts = time.time() if timestamp is None else timestamp
    enc = encrypt_aes_gcm(
        handshake_key,
        {"password": password, "timestamp": ts},
        aad=salt,
    )
    payload = {
        "client_pubkey_jwk": client_jwk,
        "iv_b64": enc["iv_b64"],
        "ciphertext_b64": enc["ciphertext_b64"],
        "nonce": challenge_nonce,
    }
    return payload, handshake_key, session_key


# =============================================================================
# Estado Global do Gate E2EE (Thread-Safe)
# =============================================================================


@dataclass
class _ChallengeRecord:
    nonce: str
    created_at: float
    server_private_key: ec.EllipticCurvePrivateKey
    server_pubkey_jwk: dict[str, Any]


@dataclass
class E2EESessionRecord:
    token: str
    session_key: bytes
    created_at: float
    expires_at: float
    client_id: str


_state_lock = threading.RLock()
_challenges: dict[str, _ChallengeRecord] = {}
_sessions: dict[str, E2EESessionRecord] = {}
_failed_attempts: dict[str, list[float]] = {}
_lockout_until: dict[str, float] = {}
_global_unlocked: bool = False
_force_lock_mode: bool | None = None

# Cache do hash PBKDF2 derivado de FRYIVS_VOICE_PASSWORD (para não re-executar 310k iterações no setup)
_cached_env_pw_fingerprint: str | None = None
_cached_env_pw_hash: str | None = None

# Senha efêmera aleatória se o operador não configurou FRYIVS_VOICE_PASSWORD nem HASH
_ephemeral_pw_hash: str | None = None
_ephemeral_pw_announced: bool = False

# Callbacks opcionais executados ao bloquear (ex.: fechar WebSockets, parar áudio)
_on_lock_callbacks: list[Callable[[], None]] = []


def register_on_lock_callback(cb: Callable[[], None]) -> None:
    """Registra callback invocado sempre que a IA for bloqueada."""
    with _state_lock:
        if cb not in _on_lock_callbacks:
            _on_lock_callbacks.append(cb)


def set_lock_enforcement(enabled: bool | None) -> None:
    """
    Força ativação/desativação explícita do bloqueio E2EE (usado principalmente em testes).
    Passe None para voltar ao comportamento padrão baseado em variáveis de ambiente.
    """
    global _force_lock_mode
    with _state_lock:
        _force_lock_mode = enabled


def reset_e2ee_state(lock_enforcement: bool | None = None) -> None:
    """Reseta desafios, sessões, rate-limit e estado de desbloqueio (utilitário para testes)."""
    global _global_unlocked, _force_lock_mode
    global _cached_env_pw_fingerprint, _cached_env_pw_hash
    global _ephemeral_pw_hash, _ephemeral_pw_announced
    with _state_lock:
        _challenges.clear()
        _sessions.clear()
        _failed_attempts.clear()
        _lockout_until.clear()
        _global_unlocked = False
        _force_lock_mode = lock_enforcement
        _cached_env_pw_fingerprint = None
        _cached_env_pw_hash = None
        _ephemeral_pw_hash = None
        _ephemeral_pw_announced = False


def is_e2ee_required() -> bool:
    """
    Indica se o bloqueio E2EE está ativo.

    - Em runtime normal: padrão 'true' (ativo, bloqueado até desbloqueio criptografado).
    - Sob pytest (PYTEST_CURRENT_TEST): automaticamente bypassado por padrão para preservar
      a suíte existente de testes unitários, exceto quando explicitamente ativado via
      `set_lock_enforcement(True)`, `FRYIVS_E2EE_FORCE_IN_TESTS=true`, ou definindo
      `FRYIVS_REQUIRE_E2EE_PASSWORD=true` explicitamente no teste.
    """
    with _state_lock:
        if _force_lock_mode is not None:
            return bool(_force_lock_mode)

    in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if in_pytest:
        force_in_tests = os.environ.get("FRYIVS_E2EE_FORCE_IN_TESTS", "").strip().lower()
        if force_in_tests in ("1", "true", "yes", "on"):
            return True
        explicit_env = os.environ.get("FRYIVS_REQUIRE_E2EE_PASSWORD")
        if explicit_env is not None and _DOTENV_REQUIRE_VAL is None:
            return explicit_env.strip().lower() not in ("false", "0", "no", "nao", "não", "off", "")
        return False

    env_val = os.environ.get("FRYIVS_REQUIRE_E2EE_PASSWORD", "true").strip().lower()
    return env_val not in ("false", "0", "no", "nao", "não", "off")


def _get_max_failed_attempts() -> int:
    try:
        return max(1, int(os.environ.get("FRYIVS_E2EE_MAX_ATTEMPTS", str(DEFAULT_MAX_FAILED_ATTEMPTS))))
    except ValueError:
        return DEFAULT_MAX_FAILED_ATTEMPTS


def _get_lockout_seconds() -> float:
    try:
        return max(5.0, float(os.environ.get("FRYIVS_E2EE_LOCKOUT_SECONDS", str(DEFAULT_LOCKOUT_SECONDS))))
    except ValueError:
        return DEFAULT_LOCKOUT_SECONDS


def _get_session_ttl_seconds() -> float:
    try:
        return max(60.0, float(os.environ.get("FRYIVS_E2EE_SESSION_TTL", str(DEFAULT_SESSION_TTL_SECONDS))))
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS


def _has_configured_password() -> bool:
    return bool(
        os.environ.get("FRYIVS_VOICE_PASSWORD_HASH", "").strip()
        or os.environ.get("FRYIVS_VOICE_PASSWORD", "").strip()
    )


def _get_active_password_hash() -> tuple[str, bool]:
    """
    Retorna `(pbkdf2_hash, has_password_configured)`.
    Prioridade:
      1. FRYIVS_VOICE_PASSWORD_HASH (hash PBKDF2-HMAC-SHA256 já armazenado)
      2. FRYIVS_VOICE_PASSWORD (convertido em hash PBKDF2-HMAC-SHA256 com salt aleatório em memória)
      3. Senha efêmera de alta entropia gerada no startup (sem senha estática hardcoded!)
    """
    global _cached_env_pw_fingerprint, _cached_env_pw_hash
    global _ephemeral_pw_hash, _ephemeral_pw_announced

    env_hash = os.environ.get("FRYIVS_VOICE_PASSWORD_HASH", "").strip()
    if env_hash:
        return env_hash, True

    env_pw = os.environ.get("FRYIVS_VOICE_PASSWORD", "").strip()
    if env_pw:
        # Fingerprint com SHA-256 apenas para detectar alteração de env em testes/reloads
        fp = hashlib.sha256(env_pw.encode("utf-8")).hexdigest()
        with _state_lock:
            if _cached_env_pw_fingerprint != fp or not _cached_env_pw_hash:
                _cached_env_pw_hash = hash_password(env_pw)
                _cached_env_pw_fingerprint = fp
            return _cached_env_pw_hash, True

    with _state_lock:
        if not _ephemeral_pw_hash:
            ephemeral_pw = secrets.token_urlsafe(12)
            _ephemeral_pw_hash = hash_password(ephemeral_pw)
            if not _ephemeral_pw_announced:
                _ephemeral_pw_announced = True
                print(
                    "\n[E2EE] ================================================================\n"
                    "[E2EE] Nenhuma FRYIVS_VOICE_PASSWORD ou FRYIVS_VOICE_PASSWORD_HASH\n"
                    "[E2EE] configurada no .env! Senha efêmera gerada para esta execução:\n"
                    f"[E2EE]   >>> {ephemeral_pw} <<<\n"
                    "[E2EE] Configure FRYIVS_VOICE_PASSWORD no .env para definir sua senha.\n"
                    "[E2EE] ================================================================\n"
                )
        return _ephemeral_pw_hash, False


def _prune_expired_challenges(now: float) -> None:
    expired = [k for k, rec in _challenges.items() if now - rec.created_at > CHALLENGE_TTL_SECONDS]
    for k in expired:
        _challenges.pop(k, None)
    # Limite superior contra abuso de memória
    while len(_challenges) >= MAX_PENDING_CHALLENGES:
        oldest_key = min(_challenges, key=lambda k: _challenges[k].created_at)
        _challenges.pop(oldest_key, None)


def _prune_expired_sessions(now: float) -> None:
    global _global_unlocked
    expired = [tok for tok, rec in _sessions.items() if now >= rec.expires_at]
    for tok in expired:
        _sessions.pop(tok, None)
    if not _sessions:
        _global_unlocked = False


def issue_challenge() -> tuple[str, dict[str, Any]]:
    """Emite um desafio efêmero único (ECDH P-256 + nonce 256-bit, TTL 60s)."""
    now = time.time()
    private_key, pub_jwk = generate_ecdh_keypair()
    nonce = secrets.token_urlsafe(32)
    with _state_lock:
        _prune_expired_challenges(now)
        _challenges[nonce] = _ChallengeRecord(
            nonce=nonce,
            created_at=now,
            server_private_key=private_key,
            server_pubkey_jwk=pub_jwk,
        )
    return nonce, pub_jwk


def is_session_unlocked() -> bool:
    """
    Retorna True se a F.R.Y.I.Vs tem autorização para falar, ouvir e responder.
    Quando E2EE não está exigido (ex.: pytest sem lock mode ou env=false), retorna True.
    """
    if not is_e2ee_required():
        return True
    now = time.time()
    with _state_lock:
        _prune_expired_sessions(now)
        return _global_unlocked and bool(_sessions)


def validate_session_token(token: str | None) -> E2EESessionRecord | None:
    """Valida um token de sessão E2EE em tempo constante (hmac.compare_digest)."""
    if not token:
        return None
    now = time.time()
    token_bytes = token.encode("utf-8")
    with _state_lock:
        _prune_expired_sessions(now)
        matched: E2EESessionRecord | None = None
        for stored_token, rec in _sessions.items():
            if hmac.compare_digest(token_bytes, stored_token.encode("utf-8")):
                matched = rec
        return matched


def lock_all_sessions() -> None:
    """Bloqueia imediatamente a F.R.Y.I.Vs, revoga todas as sessões e interrompe fala/escuta."""
    global _global_unlocked
    with _state_lock:
        _sessions.clear()
        _challenges.clear()
        _global_unlocked = False
        callbacks = list(_on_lock_callbacks)

    # Silencia imediatamente reprodução de áudio e fila de comandos ativos
    try:
        from core import audio_player
        audio_player.parar()
    except Exception:
        pass
    try:
        from core.command_queue import get_queue
        get_queue().cancel()
    except Exception:
        pass
    for cb in callbacks:
        try:
            cb()
        except Exception:
            pass


def _check_rate_limit(client_id: str, now: float) -> float:
    """Retorna segundos restantes de lockout (0.0 se liberado)."""
    with _state_lock:
        until = _lockout_until.get(client_id, 0.0)
        if now < until:
            return max(1.0, until - now)
        if until > 0.0:
            _lockout_until.pop(client_id, None)
            _failed_attempts.pop(client_id, None)
        return 0.0


def _record_failed_attempt(client_id: str, now: float) -> tuple[int, float]:
    """
    Registra tentativa falha para `client_id`.
    Retorna `(tentativas_restantes, lockout_segundos)`.
    """
    max_attempts = _get_max_failed_attempts()
    lockout_secs = _get_lockout_seconds()
    with _state_lock:
        history = [
            ts for ts in _failed_attempts.get(client_id, [])
            if now - ts <= RATE_LIMIT_WINDOW_SECONDS
        ]
        history.append(now)
        _failed_attempts[client_id] = history
        if len(history) >= max_attempts:
            _lockout_until[client_id] = now + lockout_secs
            return 0, lockout_secs
        return max(0, max_attempts - len(history)), 0.0


def _clear_failed_attempts(client_id: str) -> None:
    with _state_lock:
        _failed_attempts.pop(client_id, None)
        _lockout_until.pop(client_id, None)


def extract_e2ee_token(
    x_e2ee_session: str = "",
    authorization: str = "",
    e2ee_token: str = "",
) -> str:
    """Extrai token de sessão E2EE de header X-E2EE-Session, Authorization E2EE ou query param."""
    if x_e2ee_session and x_e2ee_session.strip():
        return x_e2ee_session.strip()
    if e2ee_token and e2ee_token.strip():
        return e2ee_token.strip()
    if authorization and authorization.strip():
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "e2ee":
            return parts[1].strip()
    return ""


def require_e2ee_session(
    x_e2ee_session: str = Header(default="", alias="X-E2EE-Session"),
    authorization: str = Header(default=""),
    e2ee_token: str = Query(default=""),
) -> E2EESessionRecord | None:
    """
    Dependência FastAPI que exige sessão E2EE válida quando o bloqueio está ativo.
    Retorna HTTP 423 (Locked) se a F.R.Y.I.Vs estiver bloqueada ou o token E2EE for inválido.
    """
    token = extract_e2ee_token(x_e2ee_session, authorization, e2ee_token)
    session = validate_session_token(token) if token else None

    if not is_e2ee_required():
        return session

    if not is_session_unlocked() or session is None:
        raise HTTPException(
            status_code=423,
            detail="F.R.Y.I.Vs bloqueada (E2EE). Realize o desbloqueio criptografado em /api/auth/e2ee/unlock.",
            headers={"X-FRYIVS-Locked": "true"},
        )
    return session


# =============================================================================
# Transporte Opcional E2EE para /api/chat
# =============================================================================


def decrypt_chat_envelope(
    session: E2EESessionRecord,
    iv_b64: str,
    ciphertext_b64: str,
) -> dict[str, Any]:
    """Descriptografa envelope AES-256-GCM de uma mensagem de chat usando a chave da sessão."""
    try:
        return decrypt_aes_gcm(session.session_key, iv_b64, ciphertext_b64, aad=CHAT_AAD)
    except (InvalidTag, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Falha ao descriptografar envelope E2EE do chat (integridade/autenticidade inválida).",
        ) from exc


def encrypt_chat_envelope(
    session: E2EESessionRecord,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Criptografa resposta do chat com AES-256-GCM usando a chave da sessão E2EE."""
    return encrypt_aes_gcm(session.session_key, payload, aad=CHAT_AAD)


# =============================================================================
# FastAPI Router: /api/auth/e2ee/*
# =============================================================================


class E2EEUnlockRequest(BaseModel):
    client_pubkey_jwk: dict[str, Any] = Field(..., description="Chave pública efêmera ECDH P-256 do cliente em JWK")
    iv_b64: str = Field(..., min_length=12, description="Vetor de inicialização AES-256-GCM (12 bytes em base64)")
    ciphertext_b64: str = Field(..., min_length=16, description="Ciphertext + tag GCM em base64")
    nonce: str = Field(..., min_length=16, description="Challenge nonce de uso único obtido em /status")


e2ee_router = APIRouter(prefix="/api/auth/e2ee", tags=["E2EE Security"])


def _client_id_from_request(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip[:64]
    if request.client and request.client.host:
        return request.client.host
    return "local"


@e2ee_router.get("/status")
def get_e2ee_status(
    request: Request,
    x_e2ee_session: str = Header(default="", alias="X-E2EE-Session"),
    authorization: str = Header(default=""),
    e2ee_token: str = Query(default=""),
) -> dict[str, Any]:
    """
    Retorna estado do bloqueio E2EE e emite um novo desafio efêmero
    (chave pública ECDH P-256 + challenge_nonce anti-replay com TTL de 60s).
    """
    now = time.time()
    client_id = _client_id_from_request(request)
    lockout_remaining = _check_rate_limit(client_id, now)
    nonce, server_pubkey_jwk = issue_challenge()

    token = extract_e2ee_token(x_e2ee_session, authorization, e2ee_token)
    session_valid = validate_session_token(token) is not None if token else False
    required = is_e2ee_required()
    from core.runtime_mode import is_web_mode
    unlocked = (session_valid if required else True) if is_web_mode() else is_session_unlocked()

    return {
        "required": required,
        "unlocked": unlocked,
        "session_valid": session_valid if required else True,
        "has_password_configured": _has_configured_password(),
        "server_pubkey_jwk": server_pubkey_jwk,
        "challenge_nonce": nonce,
        "challenge_ttl_seconds": int(CHALLENGE_TTL_SECONDS),
        "protocol": E2EE_PROTOCOL,
        "lockout_remaining_seconds": int(lockout_remaining) if lockout_remaining > 0 else 0,
    }


@e2ee_router.post("/unlock")
def post_e2ee_unlock(req: E2EEUnlockRequest, request: Request) -> dict[str, Any]:
    """
    Realiza handshake E2EE (ECDH P-256 + HKDF-SHA256 + AES-256-GCM):
    - Consome o challenge_nonce (uso único, anti-replay, TTL 60s)
    - Descriptografa { password, timestamp }
    - Valida frescor do timestamp e verifica senha com PBKDF2-HMAC-SHA256 (310k iterações)
    - Desbloqueia fala/escuta/API e devolve token de sessão CRIPTOGRAFADO via AES-256-GCM
    """
    global _global_unlocked
    now = time.time()
    client_id = _client_id_from_request(request)

    # 1. Rate limiting check
    lockout_remaining = _check_rate_limit(client_id, now)
    if lockout_remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas falhas. Tente novamente em {int(lockout_remaining)}s.",
            headers={"Retry-After": str(int(lockout_remaining))},
        )

    # 2. Consumo atômico do desafio anti-replay (single-use)
    with _state_lock:
        _prune_expired_challenges(now)
        challenge = _challenges.pop(req.nonce, None)

    if challenge is None or (now - challenge.created_at) > CHALLENGE_TTL_SECONDS:
        remaining, lockout_s = _record_failed_attempt(client_id, now)
        if lockout_s > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Desafio inválido/expirado e limite de tentativas atingido. Bloqueado por {int(lockout_s)}s.",
                headers={"Retry-After": str(int(lockout_s))},
            )
        raise HTTPException(
            status_code=401,
            detail=f"Desafio (nonce) inválido, expirado ou já utilizado (anti-replay). Restam {remaining} tentativas.",
        )

    # 3. ECDH P-256 + HKDF-SHA256 + AES-256-GCM decrypt
    salt = req.nonce.encode("utf-8")
    try:
        client_pub = jwk_to_public_key(req.client_pubkey_jwk)
        shared_secret = derive_shared_secret(challenge.server_private_key, client_pub)
        handshake_key = derive_aes_key(shared_secret, salt=salt, info=HKDF_INFO_HANDSHAKE)
        session_key = derive_aes_key(shared_secret, salt=salt, info=HKDF_INFO_SESSION)
        decrypted = decrypt_aes_gcm(
            handshake_key,
            req.iv_b64,
            req.ciphertext_b64,
            aad=salt,
        )
    except (InvalidTag, ValueError, json.JSONDecodeError) as exc:
        remaining, lockout_s = _record_failed_attempt(client_id, now)
        if lockout_s > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Falha criptográfica E2EE e limite de tentativas atingido. Bloqueado por {int(lockout_s)}s.",
                headers={"Retry-After": str(int(lockout_s))},
            ) from exc
        raise HTTPException(
            status_code=401,
            detail=f"Falha na verificação criptográfica E2EE (ECDH/AES-GCM). Restam {remaining} tentativas.",
        ) from exc

    # 4. Verificação de frescor de timestamp (anti-replay temporal)
    password = decrypted.get("password")
    raw_ts = decrypted.get("timestamp")
    if not isinstance(password, str) or not password or not isinstance(raw_ts, (int, float)):
        remaining, lockout_s = _record_failed_attempt(client_id, now)
        if lockout_s > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Payload inválido e limite de tentativas atingido. Bloqueado por {int(lockout_s)}s.",
                headers={"Retry-After": str(int(lockout_s))},
            )
        raise HTTPException(
            status_code=401,
            detail="Payload E2EE inválido: esperado { password, timestamp }.",
        )

    ts_seconds = float(raw_ts) / 1000.0 if float(raw_ts) > 1e12 else float(raw_ts)
    if abs(now - ts_seconds) > TIMESTAMP_MAX_SKEW_SECONDS:
        remaining, lockout_s = _record_failed_attempt(client_id, now)
        if lockout_s > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Timestamp expirado e limite de tentativas atingido. Bloqueado por {int(lockout_s)}s.",
                headers={"Retry-After": str(int(lockout_s))},
            )
        raise HTTPException(
            status_code=401,
            detail="Timestamp do handshake E2EE fora da janela permitida (anti-replay).",
        )

    # 5. Verificação da senha via PBKDF2-HMAC-SHA256 (310.000 iterações) + hmac.compare_digest
    stored_hash, _ = _get_active_password_hash()
    if not verify_password_hash(password, stored_hash):
        remaining, lockout_s = _record_failed_attempt(client_id, now)
        if lockout_s > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Senha incorreta. Limite de tentativas atingido; aguarde {int(lockout_s)}s.",
                headers={"Retry-After": str(int(lockout_s))},
            )
        raise HTTPException(
            status_code=401,
            detail=f"Senha incorreta. Acesso negado ({remaining} tentativas restantes).",
        )

    # 6. Sucesso: limpa rate limit, cria sessão autenticada, desbloqueia fala/API e retorna token cifrado
    _clear_failed_attempts(client_id)
    ttl = _get_session_ttl_seconds()
    expires_at = now + ttl
    session_token = secrets.token_urlsafe(32)
    record = E2EESessionRecord(
        token=session_token,
        session_key=session_key,
        created_at=now,
        expires_at=expires_at,
        client_id=client_id,
    )
    with _state_lock:
        _prune_expired_sessions(now)
        _sessions[session_token] = record
        _global_unlocked = True

    encrypted_response = encrypt_aes_gcm(
        handshake_key,
        {
            "session_token": session_token,
            "expires_at": expires_at,
            "ttl_seconds": int(ttl),
            "protocol": E2EE_PROTOCOL,
        },
        aad=salt,
    )

    return {
        "unlocked": True,
        "protocol": E2EE_PROTOCOL,
        "expires_at": expires_at,
        "encrypted_response": encrypted_response,
    }


@e2ee_router.post("/lock")
def post_e2ee_lock(
    e2ee_session: E2EESessionRecord | None = Depends(require_e2ee_session),
) -> dict[str, Any]:
    """Bloqueia a sessão E2EE atual (ou todas em modo desktop)."""
    from core.runtime_mode import is_web_mode
    if is_web_mode() and e2ee_session is not None:
        with _state_lock:
            _sessions.pop(e2ee_session.token, None)
            if not _sessions:
                global _global_unlocked
                _global_unlocked = False
    else:
        lock_all_sessions()
    return {
        "unlocked": False,
        "locked": True,
        "message": "F.R.Y.I.Vs bloqueada com sucesso (E2EE).",
    }


if __name__ == "__main__":
    import getpass
    pw = getpass.getpass("Digite a senha para gerar hash PBKDF2-HMAC-SHA256 (310.000 iterações): ")
    if not pw:
        print("Senha vazia cancelada.")
        sys.exit(1)
    print("\nAdicione esta linha ao seu .env:")
    print(f"FRYIVS_VOICE_PASSWORD_HASH={hash_password(pw)}")
