"""
Módulo de integração do GPTCache (Zilliz) para F.R.Y.I.Vs.
Armazena e recupera respostas de consultas conversacionais e perguntas frequentes,
acelerando o tempo de resposta da IA e economizando tokens da API do Gemini.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger("fryivs.gptcache")

_CACHE_INITIALIZED = False
_CACHE_AVAILABLE = False

_DYNAMIC_EXCLUSIONS = (
    "hora", "horas", "que horas", "data", "dia de hoje", "dia e hoje",
    "status", "bateria", "cpu", "ram", "memoria", "print", "screenshot",
    "abrir", "abra", "abre", "fechar", "feche", "fecha", "minimizar", "maximizar",
    "digitar", "clicar", "clique", "pesquise", "pesquisar", "pesquisa", "busque", "buscar",
    "procure", "procurar", "chrome", "edge", "navegador", "browser", "app", "programa",
    "youtube", "planilha", "excel", "word", "adicion", "remov", "edit", "substitu",
    "link", "resultado", "primeiro", "segundo", "terceiro", "role", "rolar", "volte", "voltar", "aba", "site"
)


def _should_bypass_cache(prompt: str) -> bool:
    """Verifica se o prompt contém comandos dinâmicos, estado ativo ou execução sob pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    p_lower = prompt.lower().strip()
    return any(exc in p_lower for exc in _DYNAMIC_EXCLUSIONS)


def init_gptcache() -> bool:
    """Inicializa o motor do GPTCache com persistência local."""
    global _CACHE_INITIALIZED, _CACHE_AVAILABLE
    if _CACHE_INITIALIZED:
        return _CACHE_AVAILABLE

    try:
        from gptcache import cache
        from gptcache.manager import get_data_manager
        from gptcache.processor.pre import get_prompt

        cache_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "gptcache_map.txt")

        dm = get_data_manager(data_path=cache_file)
        cache.init(pre_embedding_func=get_prompt, data_manager=dm)
        _CACHE_AVAILABLE = True
        logger.info("[GPTCache] Inicializado com sucesso via repositório/módulo GPTCache.")
        print("[GPTCache] Motor de cache semântico GPTCache ativado com sucesso.")
    except Exception as exc:
        logger.warning(f"[GPTCache] Não foi possível inicializar GPTCache: {exc}")
        print(f"[GPTCache] Aviso: cache desativado ({exc})")
        _CACHE_AVAILABLE = False

    _CACHE_INITIALIZED = True
    return _CACHE_AVAILABLE


def get_cached_response(prompt: str) -> Optional[str]:
    """Recupera resposta do cache GPTCache se disponível e válida."""
    if _should_bypass_cache(prompt):
        return None

    if not _CACHE_INITIALIZED:
        init_gptcache()

    if not _CACHE_AVAILABLE:
        return None

    try:
        from gptcache.adapter.api import get
        cached = get(prompt.strip())
        if cached and isinstance(cached, str) and cached.strip():
            logger.info(f"[GPTCache] Cache hit para: '{prompt[:40]}'")
            return cached.strip()
    except Exception as exc:
        logger.debug(f"[GPTCache] Erro ao consultar cache: {exc}")

    return None


def cache_response(prompt: str, response: str) -> None:
    """Armazena par pergunta/resposta no GPTCache."""
    if _should_bypass_cache(prompt):
        return

    if not response or response.startswith("Erro:") or len(response.strip()) < 5:
        return

    if not _CACHE_INITIALIZED:
        init_gptcache()

    if not _CACHE_AVAILABLE:
        return

    try:
        from gptcache.adapter.api import put
        put(prompt.strip(), response.strip())
        logger.debug(f"[GPTCache] Cache gravado para: '{prompt[:40]}'")
    except Exception as exc:
        logger.debug(f"[GPTCache] Erro ao gravar cache: {exc}")
