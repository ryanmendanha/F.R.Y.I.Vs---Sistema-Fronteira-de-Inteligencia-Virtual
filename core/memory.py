"""
Módulo de memória semântica vetorial de longo prazo para F.R.Y.I.Vs (v3 Tripartite).

Mantém 100% de compatibilidade retroativa com as assinaturas públicas
(`salvar_memoria`, `buscar_contexto`, `listar_memorias`, `deletar_memoria`),
elevando o núcleo interno com:
- Classificação taxonômica tripartite (`episodic` | `semantic` | `procedural`).
- Índice estruturado em SQLite (`core.memory_v3.MemoryV3Store`) com timestamps reais.
- Limiar de distância cosseno padrão calibrado (`0.65`) + re-ranking composto
  (`score = sim * 0.70 + recency_decay * 0.20 + importance * 0.10`).
- Deduplicação semântica (atualiza memórias quase-duplicadas em vez de duplicar)
  e filtro de ruído para comandos efêmeros ("que horas são?", "aumente o volume").
- Ordenação genuinamente cronológica (mais recentes primeiro) em `listar_memorias()`.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from core.memory_v3 import (
    DEFAULT_COSINE_THRESHOLD,
    EPISODIC_DEDUP_MAX_DISTANCE,
    MEMORY_TYPE_EPISODIC,
    MEMORY_TYPE_PROCEDURAL,
    MEMORY_TYPE_SEMANTIC,
    SEMANTIC_DEDUP_MAX_DISTANCE,
    TRUST_VERIFIED_INTERNAL,
    MemoryV3Store,
    _normalizar_ascii,
    calcular_score_composto,
    classificar_memoria,
    eh_comando_efemero,
    get_default_store,
    sanitizar_conteudo_externo,
)
from core.vector_db import get_or_create_collection

COLLECTION_NAME = "fryvis_memoria"

_TS_LOCK = threading.Lock()
_LAST_TS: float = 0.0


def _proximo_timestamp(explicito: float | None = None) -> float:
    """Garante timestamp monotônico crescente quando salvo em rajadas rápidas."""
    global _LAST_TS
    if explicito is not None:
        return float(explicito)
    with _TS_LOCK:
        agora = time.time()
        if agora <= _LAST_TS:
            agora = _LAST_TS + 1e-5
        _LAST_TS = agora
        return agora


def _get_memory_collection():
    """Obtém a coleção de memória semântica com configurações otimizadas."""
    return get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _sanitizar_metadados_chroma(meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Garante tipos primitivos compatíveis com o schema de metadados do ChromaDB."""
    limpo: dict[str, str | int | float | bool] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            limpo[str(k)] = v
        else:
            limpo[str(k)] = str(v)
    return limpo


def _extrair_timestamp_meta(
    meta: dict[str, Any] | None,
    sqlite_meta: dict[str, Any] | None = None,
    fallback: float = 0.0,
) -> float:
    """Extrai o timestamp mais confiável dos metadados ChromaDB ou índice SQLite."""
    for fonte in (meta or {}, sqlite_meta or {}):
        for chave in ("updated_at", "timestamp", "created_at"):
            val = fonte.get(chave)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return float(fallback)


def salvar_memoria(
    texto: str,
    id_: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    memory_type: str | None = None,
    importance: float | None = None,
    source: str = "conversation",
    trust_level: str = TRUST_VERIFIED_INTERNAL,
    forcar: bool = False,
    store: MemoryV3Store | None = None,
) -> bool:
    """
    Salva (ou atualiza via deduplicação semântica) um texto na memória vetorial
    tripartite do ChromaDB e registra metadados estruturados em `memory_v3` SQLite.

    Args:
        texto: Conteúdo textual a ser memorizado.
        id_: Identificador único opcional (se omitido, gera UUID4).
        metadata: Dicionário opcional de atributos extras.
        memory_type: Tipo taxonômico opcional ('episodic', 'semantic', 'procedural').
        importance: Peso de importância opcional em [0.0, 1.0].
        source: Origem do registro ('conversation', 'second_brain', 'skill', etc.).
        trust_level: Nível de confiança ('verified_internal' | 'external_sanitized').
        forcar: Se True, ignora filtro de comandos efêmeros e deduplicação.
        store: Instância opcional de `MemoryV3Store` (útil para testes isolados).
    """
    if not texto or not texto.strip():
        return False

    texto_limpo = texto.strip()

    if not forcar and eh_comando_efemero(texto_limpo):
        return False

    meta_in = dict(metadata) if metadata else {}
    effective_trust = str(meta_in.get("trust_level") or trust_level or TRUST_VERIFIED_INTERNAL)
    effective_source = str(meta_in.get("source") or source or "conversation")

    # Sanitiza conteúdo externo antes de gravar na memória de longo prazo
    if effective_trust != TRUST_VERIFIED_INTERNAL:
        texto_limpo, flags = sanitizar_conteudo_externo(texto_limpo, aplicar_tag=False)
        if not texto_limpo:
            return False
        if flags:
            meta_in["sanitized"] = True
            meta_in["injection_flags"] = ",".join(flags)

    if memory_type is not None:
        meta_in["memory_type"] = memory_type
    if importance is not None:
        meta_in["importance"] = importance

    mem_type, imp = classificar_memoria(texto_limpo, meta_in)

    # Respeita timestamp explícito (útil para testes determinísticos de recency decay)
    ts_explicito: float | None = None
    for chave_ts in ("timestamp", "created_at"):
        if chave_ts in meta_in and meta_in[chave_ts] is not None:
            try:
                ts_explicito = float(meta_in[chave_ts])
                break
            except (TypeError, ValueError):
                pass
    agora = _proximo_timestamp(ts_explicito)
    updated_explicito = meta_in.get("updated_at")
    updated_at = float(updated_explicito) if updated_explicito is not None else agora

    active_store = store if store is not None else get_default_store()

    try:
        col = _get_memory_collection()
        target_id = id_ or str(uuid.uuid4())
        created_at = agora

        # Deduplicação semântica (atualiza registro quase-duplicado em vez de duplicar)
        if not forcar:
            try:
                total = col.count()
            except Exception:
                total = 0

            if total > 0:
                dedup_dist = (
                    SEMANTIC_DEDUP_MAX_DISTANCE
                    if mem_type in (MEMORY_TYPE_SEMANTIC, MEMORY_TYPE_PROCEDURAL)
                    else EPISODIC_DEDUP_MAX_DISTANCE
                )
                try:
                    vizinho = col.query(
                        query_texts=[texto_limpo],
                        n_results=1,
                        include=["documents", "distances", "metadatas"],
                    )
                    v_ids = vizinho.get("ids", [[]])[0]
                    v_docs = vizinho.get("documents", [[]])[0]
                    v_dists = vizinho.get("distances", [[]])[0]
                    v_metas = vizinho.get("metadatas", [[]])[0]

                    if v_ids and v_dists:
                        existing_id = str(v_ids[0])
                        existing_doc = str(v_docs[0]) if v_docs else ""
                        existing_dist = float(v_dists[0])
                        existing_meta = dict(v_metas[0] or {}) if v_metas else {}

                        eh_texto_identico = _normalizar_ascii(existing_doc) == _normalizar_ascii(texto_limpo)
                        eh_quase_duplicata = existing_dist <= dedup_dist

                        if eh_texto_identico or eh_quase_duplicata:
                            target_id = existing_id
                            old_ts = existing_meta.get("created_at") or existing_meta.get("timestamp")
                            if old_ts is not None:
                                try:
                                    created_at = float(old_ts)
                                except (TypeError, ValueError):
                                    pass
                            old_imp = existing_meta.get("importance")
                            if old_imp is not None:
                                try:
                                    imp = max(imp, float(old_imp))
                                except (TypeError, ValueError):
                                    pass
                except Exception:
                    # Falha na busca de deduplicação nunca deve impedir o salvamento
                    pass

        meta_final: dict[str, Any] = dict(meta_in)
        meta_final.update({
            "timestamp": float(updated_at),
            "created_at": float(created_at),
            "updated_at": float(updated_at),
            "memory_type": mem_type,
            "importance": float(imp),
            "source": effective_source,
            "trust_level": effective_trust,
        })

        col.upsert(
            documents=[texto_limpo],
            ids=[target_id],
            metadatas=[_sanitizar_metadados_chroma(meta_final)],
        )

        try:
            active_store.upsert_memory_meta(
                memory_id=target_id,
                memory_type=mem_type,
                importance=imp,
                created_at=created_at,
                updated_at=updated_at,
                source=effective_source,
                trust_level=effective_trust,
            )
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"[Memória] Erro ao salvar registro {id_}: {e}")
        return False


def buscar_contexto(
    pergunta: str,
    n_resultados: int = 3,
    threshold: float = DEFAULT_COSINE_THRESHOLD,
    *,
    memory_type: str | None = None,
    store: MemoryV3Store | None = None,
) -> str:
    """
    Busca trechos relevantes na memória semântica com limiar calibrado (`0.65`)
    e re-ranking composto (`sim * 0.70 + recency_decay * 0.20 + importance * 0.10`).

    Args:
        pergunta: Consulta ou mensagem atual do usuário.
        n_resultados: Quantidade máxima de memórias a recuperar.
        threshold: Distância máxima cosseno aceitável para inclusão (padrão 0.65).
        memory_type: Filtro opcional por tipo ('episodic' | 'semantic' | 'procedural').
        store: Instância opcional de `MemoryV3Store`.
    """
    if not pergunta or not pergunta.strip():
        return ""
    if n_resultados <= 0:
        return ""

    active_store = store if store is not None else get_default_store()

    try:
        col = _get_memory_collection()
        total = col.count()
        if total == 0:
            return ""

        n_candidates = min(max(n_resultados * 4, 12), total)
        query_kwargs: dict[str, Any] = {
            "query_texts": [pergunta.strip()],
            "n_results": n_candidates,
            "include": ["documents", "distances", "metadatas"],
        }

        if memory_type:
            try:
                filtrados = col.get(where={"memory_type": memory_type}, include=[])
                qtd_filtrada = len(filtrados.get("ids", []))
                if qtd_filtrada == 0:
                    return ""
                query_kwargs["n_results"] = min(n_candidates, qtd_filtrada)
                query_kwargs["where"] = {"memory_type": memory_type}
            except Exception:
                query_kwargs["where"] = {"memory_type": memory_type}

        resultados = col.query(**query_kwargs)

        ids = resultados.get("ids", [[]])[0]
        docs = resultados.get("documents", [[]])[0]
        distances = resultados.get("distances", [[]])[0]
        metadatas = resultados.get("metadatas", [[]])[0] or [{}] * len(docs)

        if not ids:
            ids = [f"idx-{i}" for i in range(len(docs))]

        sqlite_metas: dict[str, dict[str, Any]] = {}
        try:
            sqlite_metas = active_store.get_many_memory_meta([str(mid) for mid in ids])
        except Exception:
            sqlite_metas = {}

        agora = time.time()
        candidatos_ranqueados: list[tuple[float, float, str, str, dict[str, Any]]] = []

        for mid, doc, dist, meta in zip(ids, docs, distances, metadatas):
            if dist is None or float(dist) > threshold:
                continue
            mid_str = str(mid)
            meta_dict = dict(meta or {})
            sq_meta = sqlite_metas.get(mid_str)

            mtype = str(
                meta_dict.get("memory_type")
                or (sq_meta.get("memory_type") if sq_meta else "")
                or MEMORY_TYPE_EPISODIC
            )
            try:
                imp = float(
                    meta_dict.get("importance")
                    if meta_dict.get("importance") is not None
                    else (sq_meta.get("importance") if sq_meta else 0.5)
                )
            except (TypeError, ValueError):
                imp = 0.5

            ts = _extrair_timestamp_meta(meta_dict, sq_meta, fallback=agora)
            score = calcular_score_composto(
                cosine_distance=float(dist),
                created_at=ts,
                importance=imp,
                memory_type=mtype,
                now=agora,
            )
            candidatos_ranqueados.append((score, -float(dist), mid_str, str(doc), meta_dict))

        if not candidatos_ranqueados:
            return ""

        candidatos_ranqueados.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selecionados = candidatos_ranqueados[:n_resultados]

        documentos_relevantes: list[str] = []
        for _score, _neg_dist, mid_str, doc_text, meta_dict in selecionados:
            try:
                active_store.touch_memory(mid_str)
            except Exception:
                pass
            trust = str(meta_dict.get("trust_level") or TRUST_VERIFIED_INTERNAL)
            if trust != TRUST_VERIFIED_INTERNAL:
                doc_seguro, _ = sanitizar_conteudo_externo(
                    doc_text,
                    source=str(meta_dict.get("source") or "memory"),
                    trust_level=trust,
                    aplicar_tag=True,
                )
                documentos_relevantes.append(doc_seguro)
            else:
                documentos_relevantes.append(doc_text)

        return "\n".join(documentos_relevantes)
    except Exception as e:
        print(f"[Memória] Erro ao buscar contexto: {e}")
        return ""


def listar_memorias(
    limite: int = 50,
    *,
    memory_type: str | None = None,
    store: MemoryV3Store | None = None,
) -> list[dict[str, Any]]:
    """Lista as últimas memórias gravadas ordenadas genuinamente da mais recente para a mais antiga."""
    if limite <= 0:
        return []

    active_store = store if store is not None else get_default_store()

    try:
        col = _get_memory_collection()
        try:
            if col.count() == 0:
                return []
        except Exception:
            pass

        get_kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if memory_type:
            get_kwargs["where"] = {"memory_type": memory_type}

        dados = col.get(**get_kwargs)
        ids = dados.get("ids", []) or []
        docs = dados.get("documents", []) or []
        metas = dados.get("metadatas", []) or [{}] * len(ids)

        if not ids:
            return []

        sqlite_metas: dict[str, dict[str, Any]] = {}
        try:
            sqlite_metas = active_store.get_many_memory_meta([str(mid) for mid in ids])
        except Exception:
            sqlite_metas = {}

        registros: list[tuple[float, int, dict[str, Any]]] = []
        for idx, (id_, doc, meta) in enumerate(zip(ids, docs, metas)):
            mid_str = str(id_)
            meta_dict = dict(meta or {})
            sq_meta = sqlite_metas.get(mid_str)
            if sq_meta:
                meta_dict.setdefault("memory_type", sq_meta.get("memory_type", MEMORY_TYPE_EPISODIC))
                meta_dict.setdefault("importance", sq_meta.get("importance", 0.5))
                meta_dict.setdefault("created_at", sq_meta.get("created_at", 0.0))
                meta_dict.setdefault("updated_at", sq_meta.get("updated_at", 0.0))
                meta_dict.setdefault("access_count", sq_meta.get("access_count", 0))
                meta_dict.setdefault("trust_level", sq_meta.get("trust_level", TRUST_VERIFIED_INTERNAL))
            sort_ts = _extrair_timestamp_meta(meta_dict, sq_meta, fallback=0.0)
            registros.append(
                (sort_ts, idx, {"id": mid_str, "text": doc, "metadata": meta_dict})
            )

        registros.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in registros[:limite]]
    except Exception as e:
        print(f"[Memória] Erro ao listar memórias: {e}")
        return []


def deletar_memoria(id_: str, *, store: MemoryV3Store | None = None) -> bool:
    """Remove uma memória pelo id tanto do ChromaDB quanto do índice SQLite."""
    if not id_:
        return False
    active_store = store if store is not None else get_default_store()
    try:
        col = _get_memory_collection()
        col.delete(ids=[id_])
        try:
            active_store.delete_memory_meta(id_)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[Memória] Erro ao deletar memória {id_}: {e}")
        return False
