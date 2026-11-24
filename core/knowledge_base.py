"""
Modulo de Base de Conhecimento da F.R.Y.I.Vs (RAG Híbrido v3).

Indexa e consulta documentos Markdown/TXT da pasta base_conhecimento
no ChromaDB nativo da FRYIVS, combinando:
- Busca Híbrida com Reciprocal Rank Fusion (RRF): Vetorial Densa (ChromaDB)
  + BM25 léxico em Python puro (sem dependências pesadas extras) para alta precisão
  em termos em português, siglas técnicas (E2EE, HMAC, n8n, Hermes) e fórmulas Excel.
- Múltiplos chunks por arquivo (`max_chunks_por_arquivo=3`, removendo a trava de 1 chunk).
- Metadados de confiança (`verified_internal` vs `external_sanitized`) e sanitização
  anti-prompt-injection (`sanitizar_conteudo_externo`) na indexação e na recuperação.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from core.memory_v3 import (
    TRUST_EXTERNAL_SANITIZED,
    TRUST_VERIFIED_INTERNAL,
    sanitizar_conteudo_externo,
)

_RAIZ_FRYIVS = Path(__file__).resolve().parent.parent
BASE_CONHECIMENTO_PATH: Path = (
    _RAIZ_FRYIVS / "oragnizacoes_ideias" / "base_conhecimento"
)

COLECAO_NOME: str = "fryvis_base_conhecimento"

_MANIFEST_PATH: Path = _RAIZ_FRYIVS / "data" / "kb_manifest.json"


def _ler_manifesto() -> dict[str, str]:
    """Carrega manifesto {arquivo_relativo: sha256} do disco."""
    try:
        if _MANIFEST_PATH.exists():
            return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _salvar_manifesto(manifesto: dict[str, str]) -> None:
    """Persiste manifesto no disco de forma atômica."""
    try:
        _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _MANIFEST_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_MANIFEST_PATH)
    except Exception as e:
        print(f"[KnowledgeBase] Aviso: nao foi possivel salvar manifesto: {e}")


_EXTENSOES_VALIDAS: set[str] = {".md", ".txt"}
_PASTAS_IGNORADAS: set[str] = {
    "ferramentas", "chroma_db", "__pycache__", ".git", "node_modules"
}
_PASTAS_EXTERNAS: set[str] = {
    "segundo_cerebro", "_quarentena", "quarentena", "externo", "external", "web"
}

_TAMANHO_MAX_CHUNK: int = 1500
_SOBREPOSICAO: int = 150
_TOP_K_PADRAO: int = 5
_MAX_CHUNKS_POR_ARQUIVO_PADRAO: int = 3
_RRF_K: int = 60

# Stopwords enxutas PT/EN (preservando siglas técnicas como n8n, ia, v3, r2)
_STOPWORDS: frozenset[str] = frozenset({
    "a", "as", "o", "os", "e", "ou", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "para", "por", "com", "sem", "sob",
    "sobre", "entre", "que", "qual", "quais", "como", "onde", "quando", "se", "ao",
    "aos", "pelo", "pela", "pelos", "pelas", "esse", "essa", "este", "esta", "isso",
    "isto", "mais", "menos", "muito", "muita", "tambem", "ja", "nao", "sim", "ser",
    "estar", "ter", "fazer", "foi", "sao", "era", "the", "and", "of", "to", "in",
    "is", "it", "for", "on", "with", "at", "by", "from", "an", "be", "this", "that",
})

_COMPOUND_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_./][a-z0-9]+)*")
_SIMPLE_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenizar_pt_tecnico(texto: str) -> list[str]:
    """
    Tokenizador léxico para português e termos técnicos/siglas (E2EE, HMAC-SHA256,
    n8n, Hermes, python-docx, PROCV, SOMASE). Emite tokens compostos e sub-tokens
    para garantir casamento tanto exato quanto parcial.
    """
    if not texto:
        return []
    nfkd = unicodedata.normalize("NFKD", texto)
    norm = "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()

    tokens: list[str] = []
    for match in _COMPOUND_TOKEN_RE.finditer(norm):
        comp = match.group(0)
        if len(comp) < 2 and not comp.isdigit():
            continue
        if comp not in _STOPWORDS:
            tokens.append(comp)
        if any(sep in comp for sep in ("-", "_", ".", "/")):
            for sub in _SIMPLE_TOKEN_RE.findall(comp):
                if (len(sub) >= 2 or sub.isdigit()) and sub not in _STOPWORDS and sub != comp:
                    tokens.append(sub)
    return tokens


class BM25Index:
    """
    Índice Okapi BM25 em Python puro (k1=1.5, b=0.75) com IDF não-negativo estilo Lucene.
    Projetado para trabalhar em conjunto com busca densa via Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.ids = ids
        self.documents = documents
        self.metadatas = metadatas
        self.k1 = k1
        self.b = b

        self.doc_freqs: list[Counter[str]] = []
        self.doc_lens: list[int] = []
        self.df: Counter[str] = Counter()

        for doc in documents:
            toks = tokenizar_pt_tecnico(doc)
            tf = Counter(toks)
            self.doc_freqs.append(tf)
            self.doc_lens.append(len(toks))
            for termo in tf.keys():
                self.df[termo] += 1

        self.num_docs = len(documents)
        self.avgdl = (sum(self.doc_lens) / self.num_docs) if self.num_docs > 0 else 1.0

    def _idf(self, termo: str) -> float:
        df = self.df.get(termo, 0)
        if df <= 0:
            return 0.0
        return math.log(((self.num_docs - df + 0.5) / (df + 0.5)) + 1.0)

    def score_document(self, doc_idx: int, query_tokens: list[str]) -> float:
        if not query_tokens or doc_idx < 0 or doc_idx >= self.num_docs:
            return 0.0
        tf_map = self.doc_freqs[doc_idx]
        if not tf_map:
            return 0.0
        dl = self.doc_lens[doc_idx]
        denom_norm = self.k1 * (1.0 - self.b + self.b * (dl / max(self.avgdl, 1e-9)))
        score = 0.0
        for termo in query_tokens:
            tf = tf_map.get(termo, 0)
            if tf <= 0:
                continue
            idf = self._idf(termo)
            score += idf * ((tf * (self.k1 + 1.0)) / (tf + denom_norm))
        return score

    def search(
        self,
        query: str,
        top_k: int = 20,
        habilidade: str | None = None,
    ) -> list[tuple[int, float]]:
        """Retorna lista de `(doc_idx, bm25_score)` ordenada do maior para o menor."""
        if self.num_docs == 0 or top_k <= 0:
            return []
        q_tokens = tokenizar_pt_tecnico(query)
        if not q_tokens:
            return []

        resultados: list[tuple[int, float]] = []
        for idx in range(self.num_docs):
            if habilidade:
                meta = self.metadatas[idx] or {}
                if meta.get("habilidade") != habilidade:
                    continue
            sc = self.score_document(idx, q_tokens)
            if sc > 0.0:
                resultados.append((idx, sc))

        resultados.sort(key=lambda pair: pair[1], reverse=True)
        return resultados[:top_k]


_BM25_CACHE_LOCK = threading.Lock()
_BM25_CACHE_VERSION: int = 0
_BM25_CACHE_KEY: tuple[int, int, int] | None = None
_BM25_CACHE_INDEX: BM25Index | None = None


def _invalidar_cache_bm25() -> None:
    """Invalida o cache em memória do índice BM25 após alterações na coleção."""
    global _BM25_CACHE_VERSION, _BM25_CACHE_KEY, _BM25_CACHE_INDEX
    with _BM25_CACHE_LOCK:
        _BM25_CACHE_VERSION += 1
        _BM25_CACHE_KEY = None
        _BM25_CACHE_INDEX = None


def _obter_indice_bm25(colecao: Any, total_docs: int) -> BM25Index | None:
    """Constrói ou reutiliza cache do índice BM25 sincronizado com a coleção ChromaDB."""
    global _BM25_CACHE_KEY, _BM25_CACHE_INDEX
    cache_key = (id(colecao), int(total_docs), _BM25_CACHE_VERSION)
    with _BM25_CACHE_LOCK:
        if _BM25_CACHE_KEY == cache_key and _BM25_CACHE_INDEX is not None:
            return _BM25_CACHE_INDEX

    try:
        dados = colecao.get(include=["documents", "metadatas"])
        if not isinstance(dados, dict):
            return None
        ids = list(dados.get("ids") or [])
        docs = list(dados.get("documents") or [])
        metas = list(dados.get("metadatas") or [])
        if not docs:
            return None
        if len(ids) != len(docs):
            ids = [f"bm25-{i}" for i in range(len(docs))]
        if len(metas) != len(docs):
            metas = [{} for _ in range(len(docs))]
        metas_norm = [dict(m or {}) for m in metas]
        idx = BM25Index(ids=[str(i) for i in ids], documents=[str(d) for d in docs], metadatas=metas_norm)
    except Exception:
        return None

    with _BM25_CACHE_LOCK:
        _BM25_CACHE_KEY = cache_key
        _BM25_CACHE_INDEX = idx
    return idx


def _ler_frontmatter(texto: str) -> tuple[dict[str, str], str]:
    """Extrai bloco YAML --- k: v --- do topo do arquivo."""
    meta: dict[str, str] = {}
    corpo = texto
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", texto, re.DOTALL)
    if m:
        for linha in m.group(1).splitlines():
            if ":" in linha:
                k, _, v = linha.partition(":")
                meta[k.strip()] = v.strip()
        corpo = texto[m.end():]
    return meta, corpo


def _determinar_trust_level(rel_path: Path, meta_arq: dict[str, str]) -> str:
    """
    Classifica a origem do documento como `verified_internal` ou `external_sanitized`.
    Arquivos sob `segundo_cerebro/`, `_quarentena/`, `externo/`, `web/`, ou com
    frontmatter contendo URL/fontes externas são tratados como `external_sanitized`.
    """
    explicito = (meta_arq.get("trust_level") or "").strip().lower()
    if explicito in ("external_sanitized", "external", "untrusted", "untrusted_data"):
        return TRUST_EXTERNAL_SANITIZED
    if explicito == TRUST_VERIFIED_INTERNAL:
        return TRUST_VERIFIED_INTERNAL

    partes_lower = {p.lower() for p in rel_path.parts}
    if partes_lower & _PASTAS_EXTERNAS:
        return TRUST_EXTERNAL_SANITIZED

    for chave_ext in ("source_url", "url", "fontes", "origin_url"):
        if (meta_arq.get(chave_ext) or "").strip():
            return TRUST_EXTERNAL_SANITIZED

    return TRUST_VERIFIED_INTERNAL


def _dividir_em_secoes(corpo: str) -> list[tuple[str, str]]:
    """Divide por cabecalhos ## . Retorna [(titulo, texto)]."""
    partes = re.split(r"(?m)^## ", corpo)
    secoes: list[tuple[str, str]] = []
    intro = partes[0].strip()
    if intro:
        secoes.append(("Introducao", intro))
    for p in partes[1:]:
        titulo, _, conteudo = p.partition("\n")
        secoes.append((titulo.strip(), f"## {titulo.strip()}\n{conteudo.strip()}"))
    return secoes


def _quebrar_texto(
    texto: str,
    maximo: int = _TAMANHO_MAX_CHUNK,
    sobreposicao: int = _SOBREPOSICAO,
) -> list[str]:
    """Quebra textos longos respeitando paragrafos."""
    if len(texto) <= maximo:
        return [texto]
    pedacos: list[str] = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + maximo, len(texto))
        if fim < len(texto):
            corte = texto.rfind("\n", inicio, fim)
            if corte > inicio + maximo // 2:
                fim = corte
        pedaco = texto[inicio:fim].strip()
        if pedaco:
            pedacos.append(pedaco)
        if fim >= len(texto):
            break
        inicio = max(fim - sobreposicao, inicio + 1)
    return pedacos


def _listar_arquivos() -> list[Path]:
    """Lista arquivos validos da base de conhecimento."""
    if not BASE_CONHECIMENTO_PATH.exists():
        return []
    arquivos: list[Path] = []
    for caminho in sorted(BASE_CONHECIMENTO_PATH.rglob("*")):
        if not caminho.is_file():
            continue
        if caminho.suffix.lower() not in _EXTENSOES_VALIDAS:
            continue
        if any(p in _PASTAS_IGNORADAS for p in caminho.parts):
            continue
        if caminho.name.lower() == "readme.md":
            continue
        arquivos.append(caminho)
    return arquivos


def _get_colecao():
    """Obtem ou cria a colecao ChromaDB da base de conhecimento."""
    from core.vector_db import get_or_create_collection
    return get_or_create_collection(COLECAO_NOME)


def indexar(forcar: bool = False, verbose: bool = True) -> int:
    """
    Indexa (ou re-indexa) todos os documentos da base de conhecimento.

    Usa manifesto SHA-256 por arquivo para detectar mudancas de conteudo:
    - Conteudo igual e forcar=False → pula (mesmo que os chunk_ids sejam identicos)
    - Conteudo mudou → remove chunks antigos da fonte e reinsere os novos
    - forcar=True → sempre reatuando (upsert completo)
    - Documentos externos passam por `sanitizar_conteudo_externo()` e recebem
      `trust_level="external_sanitized"`.

    Retorna o numero total de chunks indexados nesta chamada.
    """
    colecao = _get_colecao()
    manifesto = _ler_manifesto()
    manifesto_atualizado: dict[str, str] = dict(manifesto)
    total_novos = 0
    houve_alteracao = False

    arquivos = _listar_arquivos()
    arquivos_processados: set[str] = set()

    if not arquivos:
        if verbose:
            print(f"[KnowledgeBase] Nenhum arquivo encontrado em {BASE_CONHECIMENTO_PATH}")
        if BASE_CONHECIMENTO_PATH.exists() and manifesto:
            colecao = _get_colecao()
            for rel_str_removido in list(manifesto.keys()):
                try:
                    resultado = colecao.get(where={"arquivo": rel_str_removido}, include=[])
                    ids_removidos = resultado.get("ids", [])
                    if ids_removidos:
                        colecao.delete(ids=ids_removidos)
                        houve_alteracao = True
                        if verbose:
                            print(f"[KnowledgeBase] Removida fonte excluida: {rel_str_removido} ({len(ids_removidos)} chunks)")
                    manifesto_atualizado.pop(rel_str_removido, None)
                except Exception as e:
                    if verbose:
                        print(f"[KnowledgeBase] Aviso ao reconciliar {rel_str_removido}: {e}")
            _salvar_manifesto(manifesto_atualizado)
            if houve_alteracao:
                _invalidar_cache_bm25()
        return 0

    for arq in arquivos:
        rel = arq.relative_to(BASE_CONHECIMENTO_PATH)
        rel_str = rel.as_posix()
        try:
            texto = arq.read_text(encoding="utf-8")
        except Exception as e:
            if verbose:
                print(f"[KnowledgeBase] Erro ao ler {arq}: {e}")
            continue

        sha256_atual = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        arquivos_processados.add(rel_str)

        if not forcar and manifesto.get(rel_str) == sha256_atual:
            continue

        meta_arq, corpo = _ler_frontmatter(texto)
        partes = rel.parts
        categoria = partes[0] if len(partes) > 1 else "geral"
        habilidade = meta_arq.get("habilidade", partes[1] if len(partes) > 2 else "")
        trust_level = _determinar_trust_level(rel, meta_arq)

        injection_flags: list[str] = []
        sanitized_flag = "false"
        if trust_level != TRUST_VERIFIED_INTERNAL:
            corpo, injection_flags = sanitizar_conteudo_externo(corpo, aplicar_tag=False)
            sanitized_flag = "true"

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, str]] = []

        for titulo, conteudo in _dividir_em_secoes(corpo):
            for i, pedaco in enumerate(
                _quebrar_texto(conteudo, _TAMANHO_MAX_CHUNK, _SOBREPOSICAO)
            ):
                chave = f"{rel_str}::{titulo}::{i}"
                chunk_id = hashlib.md5(chave.encode()).hexdigest()
                doc_text = f"[{habilidade or categoria} | {arq.stem} | {titulo}]\n{pedaco}"
                ids.append(chunk_id)
                docs.append(doc_text)
                metas.append({
                    "categoria": categoria,
                    "habilidade": habilidade,
                    "arquivo": rel_str,
                    "secao": titulo,
                    "tags": meta_arq.get("tags", ""),
                    "trust_level": trust_level,
                    "sanitized": sanitized_flag,
                    "injection_flags": ",".join(injection_flags),
                })

        if not ids:
            manifesto_atualizado[rel_str] = sha256_atual
            continue

        if rel_str in manifesto and manifesto[rel_str] != sha256_atual:
            try:
                resultado_antigo = colecao.get(where={"arquivo": rel_str}, include=[])
                ids_antigos = resultado_antigo.get("ids", [])
                if ids_antigos:
                    colecao.delete(ids=ids_antigos)
                    if verbose:
                        print(f"[KnowledgeBase] Removidos {len(ids_antigos)} chunks antigos de {rel_str}")
            except Exception as e:
                if verbose:
                    print(f"[KnowledgeBase] Aviso ao remover chunks antigos de {rel_str}: {e}")

        colecao.upsert(ids=ids, documents=docs, metadatas=metas)
        manifesto_atualizado[rel_str] = sha256_atual
        novos_nesta = len(ids)
        total_novos += novos_nesta
        houve_alteracao = True
        if verbose:
            print(f"[KnowledgeBase] OK {rel_str} ({trust_level}) -- {novos_nesta} chunk(s)")

    if BASE_CONHECIMENTO_PATH.exists():
        fontes_removidas = set(manifesto.keys()) - arquivos_processados
        for rel_str_removido in fontes_removidas:
            try:
                resultado = colecao.get(where={"arquivo": rel_str_removido}, include=[])
                ids_removidos = resultado.get("ids", [])
                if ids_removidos:
                    colecao.delete(ids=ids_removidos)
                    houve_alteracao = True
                    if verbose:
                        print(f"[KnowledgeBase] Removida fonte excluida: {rel_str_removido} ({len(ids_removidos)} chunks)")
                manifesto_atualizado.pop(rel_str_removido, None)
            except Exception as e:
                if verbose:
                    print(f"[KnowledgeBase] Aviso ao reconciliar fonte removida {rel_str_removido}: {e}")

    _salvar_manifesto(manifesto_atualizado)
    if houve_alteracao:
        _invalidar_cache_bm25()

    if verbose:
        try:
            count = _get_colecao().count()
        except Exception:
            count = "?"
        print(f"[KnowledgeBase] Indexacao concluida. Total na colecao: {count}")

    return total_novos


def buscar_conhecimento(
    pergunta: str,
    habilidade: str | None = None,
    k: int = _TOP_K_PADRAO,
    score_minimo: float = 0.55,
    max_chunks_por_arquivo: int = _MAX_CHUNKS_POR_ARQUIVO_PADRAO,
    usar_hibrido: bool = True,
) -> str:
    """
    Busca híbrida (Vetorial Densa + BM25 via Reciprocal Rank Fusion) na base de conhecimento.

    Melhorias v3:
    - Permite múltiplos chunks por documento (`max_chunks_por_arquivo=3`, sem trava de 1 chunk).
    - Combina ranking denso do ChromaDB com ranking léxico BM25 em Python puro via RRF,
      garantindo precisão em termos em português, siglas técnicas e fórmulas Excel.
    - Sanitiza e envelopa trechos externos (`trust_level != verified_internal`) com
      `<external_knowledge trust="external_sanitized">`.
    """
    if not pergunta or not pergunta.strip() or k <= 0:
        return ""

    try:
        colecao = _get_colecao()
        total = colecao.count()
        if total == 0:
            return ""

        n_fetch = min(max(k * 4, 15), total)
        kwargs: dict[str, Any] = {
            "query_texts": [pergunta],
            "n_results": n_fetch,
            "include": ["documents", "metadatas", "distances"],
        }
        if habilidade:
            try:
                filtrados = colecao.get(where={"habilidade": habilidade}, include=[])
                qtd_filtrada = len(filtrados.get("ids", []))
                if qtd_filtrada == 0:
                    return ""
                kwargs["n_results"] = min(n_fetch, qtd_filtrada)
            except Exception:
                pass
            kwargs["where"] = {"habilidade": habilidade}

        resultado = colecao.query(**kwargs)

        d_ids = resultado.get("ids", [[]])[0]
        d_docs = resultado.get("documents", [[]])[0]
        d_metas = resultado.get("metadatas", [[]])[0] or [{}] * len(d_docs)
        d_dists = resultado.get("distances", [[]])[0]
        if not d_ids:
            d_ids = [hashlib.md5(str(doc).encode("utf-8")).hexdigest() for doc in d_docs]

        # Estruturas unificadas para fusão RRF (chave = chunk_id)
        rrf_scores: dict[str, float] = {}
        chunk_docs: dict[str, str] = {}
        chunk_metas: dict[str, dict[str, Any]] = {}
        dense_dists: dict[str, float] = {}
        bm25_scores: dict[str, float] = {}
        dense_soft_ranks: dict[str, int] = {}

        # 1. Ranking Denso (ChromaDB)
        dense_rank_valid = 0
        for raw_rank, (cid, doc, meta, dist) in enumerate(zip(d_ids, d_docs, d_metas, d_dists), start=1):
            cid_str = str(cid)
            dist_f = float(dist)
            meta_dict = dict(meta or {})
            chunk_docs[cid_str] = str(doc)
            chunk_metas[cid_str] = meta_dict
            dense_dists[cid_str] = dist_f

            if dist_f <= score_minimo:
                dense_rank_valid += 1
                rrf_scores[cid_str] = rrf_scores.get(cid_str, 0.0) + (1.0 / (_RRF_K + dense_rank_valid))
            elif dist_f <= score_minimo + 0.20:
                dense_soft_ranks[cid_str] = raw_rank

        # 2. Ranking Léxico (BM25 em Python puro)
        if usar_hibrido:
            bm25_idx = _obter_indice_bm25(colecao, total)
            if bm25_idx is not None:
                bm25_hits = bm25_idx.search(pergunta, top_k=n_fetch, habilidade=habilidade)
                q_tokens_unique = set(tokenizar_pt_tecnico(pergunta))
                _self_names = {"fryvis", "fryivs", "frives"}
                for bm25_rank, (doc_idx, bm25_sc) in enumerate(bm25_hits, start=1):
                    cid_str = bm25_idx.ids[doc_idx]
                    if cid_str not in rrf_scores:
                        doc_tf = bm25_idx.doc_freqs[doc_idx]
                        matched_terms = [t for t in q_tokens_unique if doc_tf.get(t, 0) > 0]
                        if len(q_tokens_unique) >= 2 and len(matched_terms) < 2:
                            if not any(
                                t not in _self_names and any(c.isdigit() or c in "-_./" for c in t)
                                for t in matched_terms
                            ):
                                continue
                        elif len(matched_terms) == 1 and matched_terms[0] in _self_names:
                            continue
                    chunk_docs.setdefault(cid_str, bm25_idx.documents[doc_idx])
                    chunk_metas.setdefault(cid_str, bm25_idx.metadatas[doc_idx])
                    bm25_scores[cid_str] = bm25_sc
                    rrf_scores[cid_str] = rrf_scores.get(cid_str, 0.0) + (1.0 / (_RRF_K + bm25_rank))
                    # Bônus de consenso quando o chunk também apareceu perto na busca densa
                    if cid_str in dense_soft_ranks:
                        rrf_scores[cid_str] += 0.5 / (_RRF_K + dense_soft_ranks[cid_str])

        if not rrf_scores:
            return ""

        # 3. Ordenação final por RRF DESC (desempate por BM25 DESC e distância densa ASC)
        candidatos_ordenados = sorted(
            rrf_scores.keys(),
            key=lambda cid: (
                rrf_scores[cid],
                bm25_scores.get(cid, 0.0),
                -dense_dists.get(cid, 1.0),
            ),
            reverse=True,
        )

        # 4. Seleção permitindo até `max_chunks_por_arquivo` chunks por arquivo
        limite_arquivo = max(1, int(max_chunks_por_arquivo))
        contagem_por_arquivo: dict[str, int] = {}
        trechos_vistos: set[str] = set()
        trechos_validos: list[str] = []

        for cid in candidatos_ordenados:
            if len(trechos_validos) >= k:
                break
            doc = chunk_docs[cid]
            if doc in trechos_vistos:
                continue
            meta = chunk_metas.get(cid) or {}
            arquivo = str(meta.get("arquivo", ""))
            if arquivo:
                qtd_arq = contagem_por_arquivo.get(arquivo, 0)
                if qtd_arq >= limite_arquivo:
                    continue
                contagem_por_arquivo[arquivo] = qtd_arq + 1

            trechos_vistos.add(doc)

            trust_level = str(meta.get("trust_level") or TRUST_VERIFIED_INTERNAL)
            if trust_level != TRUST_VERIFIED_INTERNAL:
                doc_seguro, _ = sanitizar_conteudo_externo(
                    doc,
                    source=arquivo or "knowledge_base",
                    trust_level=trust_level,
                    aplicar_tag=True,
                )
                trechos_validos.append(doc_seguro)
            else:
                trechos_validos.append(doc)

        if not trechos_validos:
            return ""

        return "\n\n---\n\n".join(trechos_validos)

    except Exception as e:
        print(f"[KnowledgeBase] Erro na busca: {e}")
        return ""


def status() -> dict[str, Any]:
    """Retorna informacoes sobre o estado da base de conhecimento."""
    try:
        colecao = _get_colecao()
        count = colecao.count()
    except Exception as e:
        return {"indexed": False, "count": 0, "error": str(e)}

    arquivos = _listar_arquivos()
    return {
        "indexed": count > 0,
        "count": count,
        "arquivos_disponiveis": len(arquivos),
        "caminho": str(BASE_CONHECIMENTO_PATH),
        "hybrid_rrf": True,
        "max_chunks_por_arquivo": _MAX_CHUNKS_POR_ARQUIVO_PADRAO,
    }


if __name__ == "__main__":
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Indexa a base de conhecimento da FRYIVS")
    ap.add_argument("--reset", action="store_true", help="Reindexar tudo do zero")
    ap.add_argument("--status", action="store_true", help="Exibe o status da colecao")
    args = ap.parse_args()

    sys.path.insert(0, str(_RAIZ_FRYIVS))

    if args.status:
        print(_json.dumps(status(), indent=2, ensure_ascii=False))
    else:
        indexar(forcar=args.reset, verbose=True)
