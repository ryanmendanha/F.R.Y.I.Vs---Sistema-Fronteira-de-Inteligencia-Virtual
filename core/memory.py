"""
Módulo de memória semântica vetorial de longo prazo para F.R.Y.I.Vs.
Utiliza ChromaDB com busca de similaridade por cosseno e persistência eficiente.
"""

from __future__ import annotations

import uuid
from typing import Any
from core.vector_db import get_or_create_collection

COLLECTION_NAME = "fryvis_memoria"


def _get_memory_collection():
    """Obtém a coleção de memória semântica com configurações otimizadas."""
    return get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


def salvar_memoria(texto: str, id_: str | None = None, metadata: dict[str, Any] | None = None) -> bool:
    """
    Salva um texto na memória semântica vetorial do ChromaDB.
    
    Args:
        texto: Conteúdo textual a ser memorizado
        id_: Identificador único opcional (se omitido, gera UUID4)
        metadata: Dicionário opcional de atributos
    """
    if not texto or not texto.strip():
        return False
    if not id_:
        id_ = str(uuid.uuid4())
    try:
        col = _get_memory_collection()
        metas = [metadata] if metadata else None
        col.upsert(
            documents=[texto.strip()],
            ids=[id_],
            metadatas=metas
        )
        return True
    except Exception as e:
        print(f"[Memória] Erro ao salvar registro {id_}: {e}")
        return False


def buscar_contexto(pergunta: str, n_resultados: int = 3, threshold: float = 0.85) -> str:
    """
    Busca trechos relevantes na memória semântica para enriquecer o prompt do LLM.
    
    Args:
        pergunta: Consulta ou mensagem atual do usuário
        n_resultados: Quantidade máxima de memórias a recuperar
        threshold: Distância máxima cosseno aceitável para inclusão
    """
    if not pergunta or not pergunta.strip():
        return ""
    try:
        col = _get_memory_collection()
        total = col.count()
        if total == 0:
            return ""
        
        n = min(n_resultados, total)
        resultados = col.query(
            query_texts=[pergunta.strip()],
            n_results=n,
            include=["documents", "distances"]
        )
        
        docs = resultados.get("documents", [[]])[0]
        distances = resultados.get("distances", [[]])[0]

        documentos_relevantes: list[str] = []
        for doc, dist in zip(docs, distances):
            if dist <= threshold:
                documentos_relevantes.append(doc)

        return "\n".join(documentos_relevantes)
    except Exception as e:
        print(f"[Memória] Erro ao buscar contexto: {e}")
        return ""


def listar_memorias(limite: int = 50) -> list[dict[str, Any]]:
    """Lista as últimas memórias gravadas."""
    try:
        col = _get_memory_collection()
        dados = col.get(limit=limite)
        ids = dados.get("ids", [])
        docs = dados.get("documents", [])
        metas = dados.get("metadatas", []) or [{}] * len(ids)
        
        return [
            {"id": id_, "text": doc, "metadata": meta}
            for id_, doc, meta in zip(ids, docs, metas)
        ]
    except Exception as e:
        print(f"[Memória] Erro ao listar memórias: {e}")
        return []


def deletar_memoria(id_: str) -> bool:
    """Remove uma memória pelo id."""
    if not id_:
        return False
    try:
        col = _get_memory_collection()
        col.delete(ids=[id_])
        return True
    except Exception as e:
        print(f"[Memória] Erro ao deletar memória {id_}: {e}")
        return False