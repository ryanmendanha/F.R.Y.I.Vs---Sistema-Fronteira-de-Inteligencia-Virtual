"""
Módulo de gerenciamento unificado do ChromaDB para F.R.Y.I.Vs.
Implementa os padrões da skill vector-database-engineer e vector-index-tuning:
- Registry Multiton thread-safe de PersistentClients indexado por db_path.
- Eliminação do problema de ignorar caminhos diferentes após inicialização.
- Otimização do índice vetorial HNSW (cosine distance, construction_ef=128, search_ef=64, M=16).
- Cache em memória de coleções com namespace por banco e supressão de deprecations upstream.
"""

from __future__ import annotations

import os
import threading
import warnings
from typing import TYPE_CHECKING, Any

warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"chromadb.*")
warnings.filterwarnings("ignore", message=r".*asyncio\.iscoroutinefunction.*", category=DeprecationWarning)

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

try:
    import chromadb.telemetry.product.posthog
    chromadb.telemetry.product.posthog.Posthog.capture = lambda *args, **kwargs: None
except Exception:
    pass

import chromadb
from chromadb.config import Settings

if TYPE_CHECKING:
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection

from core.runtime_mode import get_chroma_dir

_CHROMA_CLIENTS: dict[str, ClientAPI] = {}
_CHROMA_CLIENT: ClientAPI | None = None
_COLLECTIONS_CACHE: dict[str, Any] = {}
_CLIENT_LOCK = threading.Lock()
DEFAULT_DB_PATH: str = str(get_chroma_dir())

HNSW_DEFAULT_METADATA: dict[str, Any] = {
    "hnsw:space": "cosine",
    "hnsw:construction_ef": 128,
    "hnsw:search_ef": 64,
    "hnsw:M": 16,
}


def get_chroma_client(
    db_path: str = DEFAULT_DB_PATH,
    force_reload: bool = False
) -> ClientAPI:
    """
    Retorna a instância do PersistentClient para o db_path informado.
    Utiliza padrão Multiton thread-safe: reutiliza instâncias para o mesmo caminho
    sem ignorar silenciosamente requisições para caminhos diferentes.
    """
    global _CHROMA_CLIENT, _CHROMA_CLIENTS

    norm_path = os.path.abspath(os.path.normpath(db_path))

    with _CLIENT_LOCK:
        if not force_reload and norm_path in _CHROMA_CLIENTS:
            return _CHROMA_CLIENTS[norm_path]

        os.makedirs(norm_path, exist_ok=True)
        settings = Settings(
            anonymized_telemetry=False,
            is_persistent=True,
            persist_directory=norm_path
        )
        client = chromadb.PersistentClient(
            path=norm_path,
            settings=settings
        )
        _CHROMA_CLIENTS[norm_path] = client

        if norm_path == os.path.abspath(DEFAULT_DB_PATH) or _CHROMA_CLIENT is None:
            _CHROMA_CLIENT = client

        return client


def get_or_create_collection(
    name: str,
    metadata: dict[str, Any] | None = None,
    db_path: str = DEFAULT_DB_PATH
) -> Collection:
    """
    Obtém ou cria uma coleção com cache em memória isolado por banco e parâmetros HNSW otimizados.
    """
    norm_path = os.path.abspath(os.path.normpath(db_path))
    cache_key = f"{norm_path}::{name}"

    if cache_key in _COLLECTIONS_CACHE:
        return _COLLECTIONS_CACHE[cache_key]

    if name in _COLLECTIONS_CACHE and not isinstance(_COLLECTIONS_CACHE[name], dict):
        return _COLLECTIONS_CACHE[name]

    client = get_chroma_client(db_path=norm_path)
    
    collection_metadata = dict(HNSW_DEFAULT_METADATA)
    if metadata:
        collection_metadata.update(metadata)

    collection = client.get_or_create_collection(
        name=name,
        metadata=collection_metadata
    )
    _COLLECTIONS_CACHE[cache_key] = collection
    _COLLECTIONS_CACHE[name] = collection
    return collection


def reset_chroma_client(db_path: str | None = None) -> None:
    """
    Reseta clientes ChromaDB. Se db_path for None, reseta todos os clientes e caches.
    Se db_path for especificado, reseta apenas a instância daquele caminho.
    """
    global _CHROMA_CLIENT, _CHROMA_CLIENTS, _COLLECTIONS_CACHE
    with _CLIENT_LOCK:
        if db_path is None:
            _CHROMA_CLIENTS.clear()
            _COLLECTIONS_CACHE.clear()
            _CHROMA_CLIENT = None
        else:
            norm_path = os.path.abspath(os.path.normpath(db_path))
            _CHROMA_CLIENTS.pop(norm_path, None)
            keys_to_remove = [k for k in _COLLECTIONS_CACHE if k.startswith(f"{norm_path}::")]
            for k in keys_to_remove:
                _COLLECTIONS_CACHE.pop(k, None)
            if _CHROMA_CLIENT and getattr(_CHROMA_CLIENT, "_persist_directory", None) == norm_path:
                _CHROMA_CLIENT = None


def reset_collection_cache() -> None:
    """Limpa o cache de coleções em memória (útil em testes unitários)."""
    global _COLLECTIONS_CACHE
    _COLLECTIONS_CACHE.clear()


