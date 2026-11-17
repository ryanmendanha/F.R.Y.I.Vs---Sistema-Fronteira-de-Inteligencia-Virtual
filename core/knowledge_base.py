"""
Modulo de Base de Conhecimento da F.R.Y.I.Vs.

Indexa e consulta documentos Markdown/TXT da pasta base_conhecimento
no ChromaDB nativo da FRYIVS. Usa o mesmo cliente e padroes HNSW
ja estabelecidos em core/vector_db.py, sem dependencia de Ollama.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_RAIZ_FRYIVS = Path(__file__).resolve().parent.parent
BASE_CONHECIMENTO_PATH: Path = (
    _RAIZ_FRYIVS / "oragnizacoes_ideias" / "base_conhecimento"
)

COLECAO_NOME: str = "fryvis_base_conhecimento"

# Manifesto de hashes SHA-256 para detectar mudanças de conteúdo
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

_TAMANHO_MAX_CHUNK: int = 1500
_SOBREPOSICAO: int = 150
_TOP_K_PADRAO: int = 3


def _ler_frontmatter(texto: str) -> tuple[dict[str, str], str]:
    """Extrai bloco YAML --- k: v --- do topo do arquivo."""
    meta: dict[str, str] = {}
    corpo = texto
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.DOTALL)
    if m:
        for linha in m.group(1).splitlines():
            if ":" in linha:
                k, _, v = linha.partition(":")
                meta[k.strip()] = v.strip()
        corpo = texto[m.end():]
    return meta, corpo


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


def _quebrar_texto(texto: str, maximo: int = _TAMANHO_MAX_CHUNK,
                   sobreposicao: int = _SOBREPOSICAO) -> list[str]:
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
    - Conteudo mudou → remove chunks antigos da fonte e reinseore os novos
    - forcar=True → sempre reatuando (upsert completo)

    Retorna o numero total de chunks indexados nesta chamada.
    """
    colecao = _get_colecao()
    manifesto = _ler_manifesto()
    manifesto_atualizado: dict[str, str] = dict(manifesto)
    total_novos = 0

    arquivos = _listar_arquivos()
    arquivos_processados: set[str] = set()

    if not arquivos:
        if verbose:
            print(f"[KnowledgeBase] Nenhum arquivo encontrado em {BASE_CONHECIMENTO_PATH}")
        # Reconciliar fontes removidas mesmo quando a base ficou vazia
        if BASE_CONHECIMENTO_PATH.exists() and manifesto:
            colecao = _get_colecao()
            for rel_str_removido in list(manifesto.keys()):
                try:
                    resultado = colecao.get(where={"arquivo": rel_str_removido}, include=[])
                    ids_removidos = resultado.get("ids", [])
                    if ids_removidos:
                        colecao.delete(ids=ids_removidos)
                        if verbose:
                            print(f"[KnowledgeBase] Removida fonte excluida: {rel_str_removido} ({len(ids_removidos)} chunks)")
                    manifesto_atualizado.pop(rel_str_removido, None)
                except Exception as e:
                    if verbose:
                        print(f"[KnowledgeBase] Aviso ao reconciliar {rel_str_removido}: {e}")
            _salvar_manifesto(manifesto_atualizado)
        return 0


    for arq in arquivos:
        rel = arq.relative_to(BASE_CONHECIMENTO_PATH)
        rel_str = rel.as_posix()
        try:
            texto = arq.read_text(encoding="utf-8")
        except Exception as e:
            if verbose:
                print(f"[KnowledgeBase] Erro ao ler {arq}: {e}")
            # Erro de leitura NÃO significa remover chunks existentes
            continue

        # Calcula SHA-256 do conteúdo para detectar mudanças reais
        sha256_atual = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        arquivos_processados.add(rel_str)

        # Pular se conteúdo idêntico e não forçado
        if not forcar and manifesto.get(rel_str) == sha256_atual:
            continue

        meta_arq, corpo = _ler_frontmatter(texto)
        partes = rel.parts
        categoria = partes[0] if len(partes) > 1 else "geral"
        habilidade = meta_arq.get("habilidade", partes[1] if len(partes) > 2 else "")

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
                })

        if not ids:
            manifesto_atualizado[rel_str] = sha256_atual
            continue

        # Se o arquivo mudou de conteúdo, remove chunks antigos da fonte antes de reinserir
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
        if verbose:
            print(f"[KnowledgeBase] OK {rel_str} -- {novos_nesta} chunk(s)")

    # Reconciliar fontes removidas (apenas se a varredura completou sem erro fatal)
    # NÃO apaga chunks se a pasta estava inacessível
    if BASE_CONHECIMENTO_PATH.exists():
        fontes_removidas = set(manifesto.keys()) - arquivos_processados
        for rel_str_removido in fontes_removidas:
            try:
                resultado = colecao.get(where={"arquivo": rel_str_removido}, include=[])
                ids_removidos = resultado.get("ids", [])
                if ids_removidos:
                    colecao.delete(ids=ids_removidos)
                    if verbose:
                        print(f"[KnowledgeBase] Removida fonte excluida: {rel_str_removido} ({len(ids_removidos)} chunks)")
                manifesto_atualizado.pop(rel_str_removido, None)
            except Exception as e:
                if verbose:
                    print(f"[KnowledgeBase] Aviso ao reconciliar fonte removida {rel_str_removido}: {e}")

    _salvar_manifesto(manifesto_atualizado)

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
) -> str:
    """
    Busca trechos relevantes na base de conhecimento e retorna
    bloco de contexto para injetar no prompt da FRYIVS.
    """
    try:
        colecao = _get_colecao()
        if colecao.count() == 0:
            return ""

        kwargs: dict[str, Any] = {
            "query_texts": [pergunta],
            "n_results": min(k, colecao.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if habilidade:
            kwargs["where"] = {"habilidade": habilidade}

        resultado = colecao.query(**kwargs)

        docs = resultado.get("documents", [[]])[0]
        metas = resultado.get("metadatas", [[]])[0]
        dists = resultado.get("distances", [[]])[0]

        trechos_validos: list[str] = []
        fontes_vistas: set[str] = set()

        for doc, meta, dist in zip(docs, metas, dists):
            if dist > score_minimo:
                continue
            arquivo = meta.get("arquivo", "")
            if arquivo in fontes_vistas:
                continue
            fontes_vistas.add(arquivo)
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
