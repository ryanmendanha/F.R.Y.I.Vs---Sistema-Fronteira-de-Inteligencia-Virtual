/**
 * Biblioteca E2EE (End-to-End Encryption) da F.R.Y.I.Vs baseada na WebCrypto API nativa.
 *
 * Protocolo (alinhado byte-a-byte com core/e2ee_auth.py):
 * - Troca de chaves efêmera ECDH P-256 (SECP256R1) por desafio
 * - Derivação HKDF-SHA256 (32 bytes = AES-256) com salt = challenge_nonce
 *   - Chave de handshake: info = "FRYIVS-E2EE-v1-handshake"
 *   - Chave de sessão:    info = "FRYIVS-E2EE-v1-session"
 * - Criptografia autenticada AES-256-GCM (IV 96-bit + Tag 128-bit + AAD)
 * - Nenhuma senha é hardcoded nem trafega em texto claro!
 */

export interface E2EEEnvelope {
  iv_b64: string;
  ciphertext_b64: string;
}

export interface E2EEStatusResponse {
  required: boolean;
  unlocked: boolean;
  session_valid: boolean;
  has_password_configured: boolean;
  server_pubkey_jwk: JsonWebKey;
  challenge_nonce: string;
  challenge_ttl_seconds: number;
  protocol: string;
  lockout_remaining_seconds?: number;
}

export interface E2EESession {
  token: string;
  expiresAt: number;
  sessionKey: CryptoKey;
  protocol: string;
}

export class E2EEAuthError extends Error {
  status: number;
  retryAfterSeconds: number;

  constructor(message: string, status: number, retryAfterSeconds = 0) {
    super(message);
    this.name = "E2EEAuthError";
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

const HKDF_INFO_HANDSHAKE = "FRYIVS-E2EE-v1-handshake";
const HKDF_INFO_SESSION = "FRYIVS-E2EE-v1-session";
const CHAT_AAD = "FRYIVS-E2EE-CHAT-v1";
const SESSION_TOKEN_STORAGE_KEY = "fryivs_e2ee_session_token";

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

function utf8Bytes(str: string): Uint8Array<ArrayBuffer> {
  const encoded = textEncoder.encode(str);
  const buf = new ArrayBuffer(encoded.byteLength);
  const out = new Uint8Array(buf);
  out.set(encoded);
  return out;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const normalized = b64.replace(/-/g, "+").replace(/_/g, "/");
  const padLen = (4 - (normalized.length % 4)) % 4;
  const binary = atob(normalized + "=".repeat(padLen));
  const buf = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function getStoredE2EEToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeE2EEToken(token: string | null): void {
  try {
    if (token) {
      sessionStorage.setItem(SESSION_TOKEN_STORAGE_KEY, token);
    } else {
      sessionStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
    }
  } catch {
    // sessionStorage indisponível
  }
}

export function buildE2EEHeaders(
  token: string | null | undefined,
  extra: Record<string, string> = {},
): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (token) {
    headers["X-E2EE-Session"] = token;
  }
  return headers;
}

export function appendE2EETokenToUrl(
  url: string,
  token: string | null | undefined,
): string {
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}e2ee_token=${encodeURIComponent(token)}`;
}

async function deriveAesGcmKeyFromSecret(
  hkdfBaseKey: CryptoKey,
  salt: Uint8Array<ArrayBuffer>,
  info: string,
): Promise<CryptoKey> {
  return window.crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt,
      info: utf8Bytes(info),
    },
    hkdfBaseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

async function encryptJsonAesGcm(
  key: CryptoKey,
  payload: Record<string, unknown>,
  aad: Uint8Array<ArrayBuffer>,
): Promise<E2EEEnvelope> {
  const ivBuf = new ArrayBuffer(12);
  const iv = new Uint8Array(ivBuf);
  window.crypto.getRandomValues(iv);
  const plaintext = utf8Bytes(JSON.stringify(payload));
  const encryptedBuf = await window.crypto.subtle.encrypt(
    {
      name: "AES-GCM",
      iv,
      additionalData: aad,
      tagLength: 128,
    },
    key,
    plaintext,
  );
  return {
    iv_b64: bytesToBase64(iv),
    ciphertext_b64: bytesToBase64(new Uint8Array(encryptedBuf)),
  };
}

async function decryptJsonAesGcm<T = Record<string, unknown>>(
  key: CryptoKey,
  envelope: E2EEEnvelope,
  aad: Uint8Array<ArrayBuffer>,
): Promise<T> {
  const iv = base64ToBytes(envelope.iv_b64);
  const ciphertext = base64ToBytes(envelope.ciphertext_b64);
  const decryptedBuf = await window.crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv,
      additionalData: aad,
      tagLength: 128,
    },
    key,
    ciphertext,
  );
  return JSON.parse(textDecoder.decode(decryptedBuf)) as T;
}

export async function fetchE2EEStatus(
  token?: string | null,
): Promise<E2EEStatusResponse> {
  const res = await fetch("/api/auth/e2ee/status", {
    method: "GET",
    headers: buildE2EEHeaders(token),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new E2EEAuthError(
      "Não foi possível consultar o estado de segurança E2EE do servidor.",
      res.status,
    );
  }
  return (await res.json()) as E2EEStatusResponse;
}

export async function performE2EEUnlock(password: string): Promise<E2EESession> {
  if (!window.crypto || !window.crypto.subtle) {
    throw new E2EEAuthError(
      "WebCrypto API indisponível neste contexto do navegador. Acesse via localhost ou HTTPS.",
      0,
    );
  }

  // 1. Obtém chave pública efêmera P-256 do servidor e challenge_nonce único
  const status = await fetchE2EEStatus();
  if (status.lockout_remaining_seconds && status.lockout_remaining_seconds > 0) {
    throw new E2EEAuthError(
      `Muitas tentativas falhas. Tente novamente em ${status.lockout_remaining_seconds}s.`,
      429,
      status.lockout_remaining_seconds,
    );
  }

  // 2. Gera par de chaves efêmero ECDH P-256 no navegador
  const clientKeyPair = await window.crypto.subtle.generateKey(
    { name: "ECDH", namedCurve: "P-256" },
    true,
    ["deriveBits"],
  );

  const rawClientJwk = await window.crypto.subtle.exportKey(
    "jwk",
    clientKeyPair.publicKey,
  );
  const clientPubJwk: JsonWebKey = {
    kty: rawClientJwk.kty,
    crv: rawClientJwk.crv,
    x: rawClientJwk.x,
    y: rawClientJwk.y,
  };

  // 3. Importa chave pública efêmera do servidor e deriva segredo compartilhado ECDH (256 bits)
  const serverPubKey = await window.crypto.subtle.importKey(
    "jwk",
    {
      kty: status.server_pubkey_jwk.kty,
      crv: status.server_pubkey_jwk.crv,
      x: status.server_pubkey_jwk.x,
      y: status.server_pubkey_jwk.y,
    },
    { name: "ECDH", namedCurve: "P-256" },
    false,
    [],
  );

  const sharedBits = await window.crypto.subtle.deriveBits(
    { name: "ECDH", public: serverPubKey },
    clientKeyPair.privateKey,
    256,
  );

  // 4. Deriva chaves AES-256-GCM de handshake e de sessão via HKDF-SHA256
  const hkdfKey = await window.crypto.subtle.importKey(
    "raw",
    sharedBits,
    "HKDF",
    false,
    ["deriveKey"],
  );

  const nonceBytes = utf8Bytes(status.challenge_nonce);
  const handshakeKey = await deriveAesGcmKeyFromSecret(
    hkdfKey,
    nonceBytes,
    HKDF_INFO_HANDSHAKE,
  );
  const sessionKey = await deriveAesGcmKeyFromSecret(
    hkdfKey,
    nonceBytes,
    HKDF_INFO_SESSION,
  );

  // 5. Criptografa { password, timestamp } com AES-256-GCM antes de sair do navegador
  const encryptedRequest = await encryptJsonAesGcm(
    handshakeKey,
    {
      password,
      timestamp: Math.floor(Date.now() / 1000),
    },
    nonceBytes,
  );

  // 6. Envia handshake E2EE para o servidor
  const unlockRes = await fetch("/api/auth/e2ee/unlock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_pubkey_jwk: clientPubJwk,
      iv_b64: encryptedRequest.iv_b64,
      ciphertext_b64: encryptedRequest.ciphertext_b64,
      nonce: status.challenge_nonce,
    }),
  });

  if (!unlockRes.ok) {
    let detail = "Falha na autenticação criptografada.";
    try {
      const errBody = (await unlockRes.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignora corpo não-JSON
    }
    const retryAfter = Number(unlockRes.headers.get("Retry-After") || "0") || 0;
    throw new E2EEAuthError(detail, unlockRes.status, retryAfter);
  }

  const unlockData = (await unlockRes.json()) as {
    unlocked: boolean;
    protocol: string;
    expires_at: number;
    encrypted_response: E2EEEnvelope;
  };

  // 7. Descriptografa o token de sessão recebido com AES-256-GCM
  const decryptedSession = await decryptJsonAesGcm<{
    session_token: string;
    expires_at: number;
    protocol?: string;
  }>(handshakeKey, unlockData.encrypted_response, nonceBytes);

  if (!decryptedSession.session_token) {
    throw new E2EEAuthError("Resposta E2EE sem token de sessão válido.", 500);
  }

  storeE2EEToken(decryptedSession.session_token);

  return {
    token: decryptedSession.session_token,
    expiresAt: decryptedSession.expires_at,
    sessionKey,
    protocol: decryptedSession.protocol || unlockData.protocol,
  };
}

export async function lockE2EESession(token?: string | null): Promise<void> {
  storeE2EEToken(null);
  try {
    await fetch("/api/auth/e2ee/lock", {
      method: "POST",
      headers: buildE2EEHeaders(token),
    });
  } catch {
    // falha de rede não impede limpeza local
  }
}

export async function encryptChatPayload(
  sessionKey: CryptoKey,
  payload: Record<string, unknown>,
): Promise<E2EEEnvelope> {
  return encryptJsonAesGcm(sessionKey, payload, utf8Bytes(CHAT_AAD));
}

export async function decryptChatPayload<T = Record<string, unknown>>(
  sessionKey: CryptoKey,
  envelope: E2EEEnvelope,
): Promise<T> {
  return decryptJsonAesGcm<T>(sessionKey, envelope, utf8Bytes(CHAT_AAD));
}
