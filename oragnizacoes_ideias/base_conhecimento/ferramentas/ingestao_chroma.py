"""
Indexa toda a base_conhecimento no ChromaDB.

Uso:  python ingestao_chroma.py            (indexação incremental)
      python ingestao_chroma.py --reset    (apaga e recria o índice)

Cada seção '## Título' de um .md vira um chunk. Metadados guardados:
categoria (pasta), habilidade, arquivo, seção, tags.
"""
import argparse
import hashlib
import re

import chromadb
import ollama

import config


def ler_frontmatter(texto: str):
    """Separa o bloco --- chave: valor --- do restante do texto."""
    meta, corpo = {}, texto
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.DOTALL)
    if m:
        for linha in m.group(1).splitlines():
            if ":" in linha:
                k, v = linha.split(":", 1)
                meta[k.strip()] = v.strip()
        corpo = texto[m.end():]
    return meta, corpo


def dividir_em_secoes(corpo: str):
    """Divide por cabeçalhos '## '. Retorna lista de (titulo, texto)."""
    partes = re.split(r"(?m)^## ", corpo)
    secoes = []
    intro = partes[0].strip()
    if intro:
        secoes.append(("Introdução", intro))
    for p in partes[1:]:
        titulo, _, texto = p.partition("\n")
        secoes.append((titulo.strip(), f"## {titulo.strip()}\n{texto.strip()}"))
    return secoes


def quebrar_texto(texto: str, maximo: int, sobreposicao: int):
    """Quebra seções muito longas respeitando parágrafos quando possível."""
    if len(texto) <= maximo:
        return [texto]
    pedacos, inicio = [], 0
    while inicio < len(texto):
        fim = min(inicio + maximo, len(texto))
        if fim < len(texto):
            corte = texto.rfind("\n", inicio, fim)
            if corte > inicio + maximo // 2:
                fim = corte
        pedacos.append(texto[inicio:fim].strip())
        if fim >= len(texto):
            break
        inicio = max(fim - sobreposicao, inicio + 1)
    return [p for p in pedacos if p]


def listar_arquivos():
    for caminho in sorted(config.RAIZ_BASE.rglob("*")):
        if not caminho.is_file() or caminho.suffix.lower() not in config.EXTENSOES:
            continue
        if any(p in config.PASTAS_IGNORADAS for p in caminho.parts):
            continue
        if caminho.name.lower() == "readme.md":
            continue
        yield caminho


def gerar_embedding(texto: str):
    return ollama.embeddings(model=config.MODELO_EMBEDDING, prompt=texto)["embedding"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="recria a coleção do zero")
    args = ap.parse_args()

    cliente = chromadb.PersistentClient(path=str(config.CAMINHO_CHROMA))
    if args.reset:
        try:
            cliente.delete_collection(config.NOME_COLECAO)
            print("Coleção anterior removida.")
        except Exception:
            pass
    colecao = cliente.get_or_create_collection(
        config.NOME_COLECAO, metadata={"hnsw:space": "cosine"}
    )

    total = 0
    for arq in listar_arquivos():
        rel = arq.relative_to(config.RAIZ_BASE)
        texto = arq.read_text(encoding="utf-8")
        meta, corpo = ler_frontmatter(texto)
        categoria = rel.parts[0]
        habilidade = meta.get("habilidade", rel.parts[1] if len(rel.parts) > 2 else "")

        ids, docs, metas, embs = [], [], [], []
        for titulo, conteudo in dividir_em_secoes(corpo):
            for i, pedaco in enumerate(
                quebrar_texto(conteudo, config.TAMANHO_MAX_CHUNK, config.SOBREPOSICAO)
            ):
                chave = f"{rel.as_posix()}::{titulo}::{i}"
                ids.append(hashlib.md5(chave.encode()).hexdigest())
                # Prefixo de contexto melhora a busca semântica
                doc = f"[{habilidade or categoria} | {arq.stem} | {titulo}]\n{pedaco}"
                docs.append(doc)
                embs.append(gerar_embedding(doc))
                metas.append({
                    "categoria": categoria,
                    "habilidade": habilidade,
                    "arquivo": rel.as_posix(),
                    "secao": titulo,
                    "tags": meta.get("tags", ""),
                })
        if ids:
            colecao.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
            total += len(ids)
            print(f"✔ {rel.as_posix()}  ({len(ids)} chunks)")

    print(f"\nConcluído: {total} chunks indexados. Total na coleção: {colecao.count()}")


if __name__ == "__main__":
    main()
