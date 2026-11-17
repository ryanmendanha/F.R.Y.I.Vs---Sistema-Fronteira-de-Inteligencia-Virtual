"""
Estado de sessão em tempo real da F.R.Y.I.Vs ("Modo Supercomputador").

Mantém de forma thread-safe:
1. Histórico unificado de conversação (voz + chat web), limitado aos últimos turnos.
2. Artefatos ativos por categoria (planilha Excel, documento Word, página Web) e o
   último artefato manipulado, permitindo comandos contínuos sem precisar repetir
   o nome do arquivo (ex.: "adicione uma linha com Mouse, 3 unidades").
"""

from __future__ import annotations

import threading
import time
from typing import Any, Final

MAX_TURNOS_HISTORICO: Final[int] = 8

_lock = threading.Lock()
_historico: list[dict[str, str]] = []
_artefato_atual: dict[str, Any] | None = None
_artefatos_por_tipo: dict[str, dict[str, Any]] = {}


def registrar_turno(mensagem_usuario: str, resposta_assistente: str) -> None:
    """Registra um par de interação (usuário -> assistente) no histórico da sessão."""
    u = (mensagem_usuario or "").strip()
    a = (resposta_assistente or "").strip()
    if not u and not a:
        return
    with _lock:
        if u:
            _historico.append({"role": "user", "content": u})
        if a:
            _historico.append({"role": "assistant", "content": a})
        if len(_historico) > MAX_TURNOS_HISTORICO:
            del _historico[:-MAX_TURNOS_HISTORICO]


def obter_historico(limite: int = MAX_TURNOS_HISTORICO) -> list[dict[str, str]]:
    """Retorna cópia dos últimos turnos do histórico."""
    with _lock:
        if limite <= 0:
            return []
        return [dict(m) for m in _historico[-limite:]]


def mesclar_historico(historico_externo: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """
    Se o cliente enviou histórico explícito não-vazio, normaliza e usa;
    caso contrário, retorna o histórico acumulado na sessão do servidor.
    """
    if historico_externo:
        normalizado: list[dict[str, str]] = []
        for item in historico_externo[-MAX_TURNOS_HISTORICO:]:
            if isinstance(item, dict):
                role = str(item.get("role", "user")).strip()
                content = str(item.get("content") or item.get("text") or "").strip()
                if content:
                    normalizado.append({"role": role, "content": content})
        if normalizado:
            return normalizado
    return obter_historico()


def registrar_artefato(
    tipo: str,
    caminho: str = "",
    url: str = "",
    titulo: str = "",
    aba: str = "",
    colunas: list[str] | None = None,
) -> dict[str, Any]:
    """
    Registra o artefato ativo (tipo: 'excel' | 'word' | 'web').
    """
    tipo_norm = (tipo or "").strip().lower()
    aba_str = str(aba or "").strip()
    titulo_str = str(titulo or aba_str or "").strip()
    info: dict[str, Any] = {
        "tipo": tipo_norm,
        "caminho": str(caminho or "").strip(),
        "url": str(url or "").strip(),
        "titulo": titulo_str,
        "aba": aba_str or titulo_str,
        "colunas": list(colunas) if colunas else [],
        "atualizado_em": time.time(),
    }
    with _lock:
        global _artefato_atual
        _artefato_atual = info
        if tipo_norm:
            _artefatos_por_tipo[tipo_norm] = info
    try:
        from pathlib import Path
        from core.overlay import status_overlay
        alvo = titulo_str or info["url"] or (Path(info["caminho"]).name if info["caminho"] else "")
        etiqueta = {"web": "WEB", "excel": "EXCEL", "word": "WORD"}.get(tipo_norm, tipo_norm.upper() or "EXTERNO")
        status_overlay(f"● MODO CO-PILOTO ({etiqueta}): {alvo[:46]}", ativo=True, duracao=180.0)
    except Exception:
        pass
    return dict(info)


def obter_artefato(tipo: str | None = None) -> dict[str, Any] | None:
    """
    Retorna o artefato ativo. Se `tipo` for informado ('excel', 'word', 'web'),
    retorna o último artefato daquele tipo específico.
    """
    with _lock:
        if tipo:
            item = _artefatos_por_tipo.get(tipo.strip().lower())
            return dict(item) if item else None
        return dict(_artefato_atual) if _artefato_atual else None


def contexto_para_llm() -> str:
    """
    Gera um bloco conciso de contexto com os artefatos ativos em segundo plano
    para que o LLM saiba qual planilha, documento ou site editar em comandos de continuação.
    """
    with _lock:
        if not _artefatos_por_tipo and not _artefato_atual:
            return ""
        partes: list[str] = ["[Artefatos Abertos em Segundo Plano]:"]
        excel = _artefatos_por_tipo.get("excel")
        if excel and excel.get("caminho"):
            aba_info = f" (aba: {excel['aba']})" if excel.get("aba") else ""
            cols = ", ".join(str(c) for c in (excel.get("colunas") or []))
            col_txt = f" (colunas: {cols})" if cols else ""
            partes.append(f"- Planilha Excel ativa: '{excel['caminho']}'{aba_info}{col_txt}")
        word = _artefatos_por_tipo.get("word")
        if word and word.get("caminho"):
            partes.append(f"- Documento Word ativo: '{word['caminho']}'")
        web = _artefatos_por_tipo.get("web")
        if web and (web.get("url") or web.get("titulo")):
            t = f" ({web['titulo']})" if web.get("titulo") else ""
            partes.append(f"- Navegador Co-Piloto ativo em: {web.get('url', '')}{t}")
        partes.append(
            "Se o senhor pedir para adicionar, editar, remover ou consultar dados sem citar "
            "outro nome de arquivo, utilize automaticamente o artefato ativo correspondente."
        )
        return "\n".join(partes)


def limpar_sessao() -> None:
    """Limpa o histórico e artefatos ativos (usado em testes)."""
    with _lock:
        global _artefato_atual
        _historico.clear()
        _artefatos_por_tipo.clear()
        _artefato_atual = None


limpar = limpar_sessao
