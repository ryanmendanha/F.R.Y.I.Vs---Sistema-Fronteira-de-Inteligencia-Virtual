"""
Script que gera o arquivo data/respostas_cache.json a partir de respostas_preindexadas.md.
Pré-calcula os embeddings de todas as 268 perguntas para busca semântica instantânea (<10ms).
"""
import re
import json
import unicodedata
from pathlib import Path
import numpy as np
import chromadb.utils.embedding_functions as ef

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "respostas_preindexadas.md"
OUT_PATH = ROOT / "data" / "respostas_cache.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def normalizar_chave(texto: str) -> str:
    """Normaliza texto: lowercase, remove acentos e pontuação, colapsa espaços."""
    t = texto.lower().strip()
    # Remove pontuação
    t = re.sub(r"[^\w\s]", "", t)
    # Remove acentos
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def main():
    content = MD_PATH.read_text(encoding="utf-8")
    pattern = r'###\s+(r\d+)\s*\n\n\*\*Perguntas:\*\*\s*\n\n(.*?)\n\n\*\*Resposta:\*\*\s*\n\n>\s*(.+?)(?=\n\n###|\n\n##|\Z)'
    matches = list(re.finditer(pattern, content, re.DOTALL))

    print(f"[Gerador] Encontrados {len(matches)} blocos de respostas.")

    pares = []
    lookup_exato = {}

    for m in matches:
        rid, pergs_raw, resp = m.groups()
        resp_clean = " ".join(resp.strip().split())
        pergs = [p.strip().lstrip("-").strip() for p in pergs_raw.strip().splitlines() if p.strip()]

        for p in pergs:
            pares.append({
                "id": rid,
                "pergunta": p,
                "resposta": resp_clean
            })
            norm = normalizar_chave(p)
            if norm:
                lookup_exato[norm] = resp_clean

    print(f"[Gerador] {len(pares)} perguntas a codificar. Calculando embeddings...")

    # Usa o modelo padrão ONNX do ChromaDB (384 dimensões, rápido e local)
    default_ef = ef.DefaultEmbeddingFunction()
    textos = [item["pergunta"] for item in pares]
    raw_embeddings = default_ef(textos)

    embs = np.array(raw_embeddings, dtype=np.float32)
    # Normalizar para norma unitária (para produto escalar = cosseno)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    embs = embs / (norms + 1e-9)

    saida_itens = []
    for item, emb in zip(pares, embs):
        saida_itens.append({
            "id": item["id"],
            "pergunta": item["pergunta"],
            "resposta": item["resposta"],
            "embedding": [round(float(x), 6) for x in emb]
        })

    dados_finais = {
        "version": "1.0",
        "total_respostas": len(matches),
        "total_perguntas": len(pares),
        "lookup_exato": lookup_exato,
        "itens": saida_itens
    }

    OUT_PATH.write_text(json.dumps(dados_finais, ensure_ascii=False, indent=2), encoding="utf-8")
    tamanho_kb = OUT_PATH.stat().st_size // 1024
    print(f"[Gerador] Sucesso! Gerado {OUT_PATH} ({tamanho_kb} KB, {len(saida_itens)} itens).")


if __name__ == "__main__":
    main()

