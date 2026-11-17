"""
Detector da palavra de ativação (wake word) da F.R.Y.I.Vs.

Recebe o TEXTO já transcrito pelo Whisper e decide se o usuário chamou a assistente
("FRYIVS", "Fraives", "Frives" e variações fonéticas). Módulo puro, sem acesso ao
microfone, para ser testado de forma determinística.

Calibrado com a amostra voz-capta/voz.m4a: o Whisper transcreve a pronúncia do
usuário como "Frives" em 5/5 repetições.
"""

from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Final

VARIANTES: Final[frozenset[str]] = frozenset({
    "fryivs", "fryvis", "frives", "fraives", "fraivis", "frayvis", "fraivs",
    "fraivz", "frivis", "friives", "fraive", "fraivis", "frayves", "fryves",
})

NEGATIVOS: Final[frozenset[str]] = frozenset({
    "drive", "drives", "frio", "frios", "fria", "frias", "five", "fries", "frevo",
    "frete", "fretes", "frevos", "privê", "prive", "livros", "frisa", "frita",
    "fritas", "frutas", "fruta", "friso", "frase", "frases", "fresco", "frisos",
    "frei", "freis", "freios", "freio", "fraco", "fracos", "frade",
})

LIMIAR_PADRAO: Final[float] = 0.80


def _limiar() -> float:
    try:
        return float(os.getenv("WAKE_WORD_THRESHOLD", LIMIAR_PADRAO))
    except ValueError:
        return LIMIAR_PADRAO


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e sem pontuação (mantém espaços)."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"(?<=[a-z])\.(?=[a-z])", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _similaridade(token: str) -> float:
    return max(SequenceMatcher(None, token, v).ratio() for v in VARIANTES)


def _eh_nome(token: str, limiar: float) -> bool:
    if not token.startswith("fr") or token in NEGATIVOS or len(token) < 5:
        return False
    return token in VARIANTES or _similaridade(token) >= limiar


def contem_nome(texto: str, limiar: float | None = None) -> tuple[bool, str]:
    """
    Verifica se o texto contém o nome da assistente.

    Returns:
        (True, resto_da_frase) quando encontrado. Ex.: "Frives, crie uma planilha"
        -> (True, "crie uma planilha"). Caso contrário (False, "").
    """
    lim = _limiar() if limiar is None else limiar
    toks = normalizar(texto).split()
    if not toks:
        return False, ""

    qtd_nomes = sum(1 for t in toks if _eh_nome(t, lim))
    if qtd_nomes >= 2:
        nao_nomes = [t for t in toks if not _eh_nome(t, lim)]
        if len(nao_nomes) <= 2:
            return False, ""

    for i, tok in enumerate(toks):
        candidatos = [(tok, 1)]
        if i + 1 < len(toks):
            candidatos.append((tok + toks[i + 1], 2))
        for cand, consumidos in candidatos:
            if _eh_nome(cand, lim):
                resto = " ".join(toks[i + consumidos:]).strip()
                return True, resto
    return False, ""


def comando_util(resto: str) -> bool:
    """Indica se o resto da frase tem conteúdo suficiente para ser um pedido."""
    letras = re.sub(r"[^a-z]", "", normalizar(resto))
    if len(letras) < 4:
        return False
    return not all(_eh_nome(t, _limiar()) for t in normalizar(resto).split())

