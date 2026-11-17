"""
Módulo de cliente e integração com o Google AI Studio (Gemini Flash) para F.R.Y.I.Vs.
Utiliza a API oficial v1beta com failover resiliente entre modelos e controle de tokens.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Final
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY: Final[str] = os.getenv("GEMINI_API_KEY", "")
PREFERRED_MODEL: Final[str] = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

def _clean_schema_for_gemini(schema: Any) -> Any:
    """Remove campos incompatíveis com a OpenAPI schema do Gemini (como title, default)."""
    if isinstance(schema, dict):
        cleaned = {}
        for k, v in schema.items():
            if k in ("title", "default"):
                continue
            cleaned[k] = _clean_schema_for_gemini(v)
        return cleaned
    elif isinstance(schema, list):
        return [_clean_schema_for_gemini(item) for item in schema]
    return schema


FALLBACK_MODELS: Final[list[str]] = list(dict.fromkeys([
    PREFERRED_MODEL,
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
]))


def is_gemini_configured() -> bool:
    """Verifica se a chave da API do Google AI Studio está configurada."""
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())


def is_gemini_online() -> bool:
    """Realiza uma checagem rápida de disponibilidade da API do Gemini sem expor a chave na URL."""
    if not is_gemini_configured():
        return False
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _format_history_for_gemini(
    history: list[dict[str, str]] | None
) -> list[dict[str, Any]]:
    """Converte histórico do formato padrão (role: user/assistant) para o formato do Gemini (user/model)."""
    if not history:
        return []

    gemini_contents: list[dict[str, Any]] = []
    for msg in history[-6:]:
        role = msg.get("role", "user")
        content = msg.get("content", "") or msg.get("text", "")
        if not content:
            continue
        gemini_role = "model" if role in ("assistant", "model") else "user"
        gemini_contents.append({
            "role": gemini_role,
            "parts": [{"text": str(content)}]
        })

    validated: list[dict[str, Any]] = []
    expected_role = "user"
    for item in gemini_contents:
        if item["role"] == expected_role:
            validated.append(item)
            expected_role = "model" if expected_role == "user" else "user"

    return validated


def ask_gemini(
    prompt: str,
    system_instruction: str = "",
    context: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    max_tokens: int = 50,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """
    Envia uma mensagem para o Google AI Studio (Gemini Flash) e retorna a resposta formatada
    e eventuais chamadas de ferramentas (functionCall).
    """
    if not is_gemini_configured():
        return "Erro: Chave de API do Google AI Studio não configurada no arquivo .env, senhor.", []

    full_system = system_instruction
    if context:
        full_system += f"\n\nContexto relevante da memória:\n{context}"

    contents = _format_history_for_gemini(conversation_history)
    if contents and contents[-1].get("role") == "user":
        contents.pop()
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max(max_tokens, 40)
        }
    }

    if full_system:
        payload["systemInstruction"] = {
            "parts": [{"text": full_system}]
        }

    if tools:
        func_decls: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function") if isinstance(t, dict) and "function" in t else t
            if isinstance(fn, dict) and "name" in fn:
                decl: dict[str, Any] = {
                    "name": fn["name"],
                    "description": fn.get("description", "")
                }
                if "parameters" in fn:
                    decl["parameters"] = _clean_schema_for_gemini(fn["parameters"])
                func_decls.append(decl)
        if func_decls:
            payload["tools"] = [{"functionDeclarations": func_decls}]

    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    last_error: str = ""
    tried_models: list[str] = []
    for model in FALLBACK_MODELS:
        if model in tried_models:
            continue
        tried_models.append(model)

        clean_model = model.replace("models/", "")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"

        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=18) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if not candidates:
                    continue

                content_obj = candidates[0].get("content", {})
                parts = content_obj.get("parts", [])
                
                tool_calls: list[dict[str, Any]] = []
                text_parts: list[str] = []
                
                for part in parts:
                    if "functionCall" in part:
                        fc = part["functionCall"]
                        tool_calls.append({
                            "function": {
                                "name": fc.get("name", ""),
                                "arguments": fc.get("args", {})
                            }
                        })
                    elif "text" in part:
                        text_parts.append(part["text"])

                if tool_calls:
                    return " ".join(text_parts).strip(), tool_calls
                if text_parts:
                    return " ".join(text_parts).strip(), []
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            if e.code in (503, 502, 429, 404):
                print(f"[Gemini] Modelo '{clean_model}' indisponível ({e.code}). Tentando fallback...")
                continue
            break
        except Exception as e:
            last_error = str(e)
            print(f"[Gemini] Exceção na chamada de '{clean_model}': {e}")
            break

    return f"Não foi possível obter resposta do Gemini Cloud no momento ({last_error}), senhor.", []
