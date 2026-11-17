"""
Consulta a base e responde com o Llama 3.2 usando os trechos recuperados (RAG).

Uso:  python consultar.py "sua pergunta"
      python consultar.py "sua pergunta" --habilidade excel_avancado
Importável:  from consultar import buscar_contexto, responder
"""
import argparse

import chromadb
import ollama

import config

PROMPT_SISTEMA = (
    "Você é um assistente especialista. Responda em português do Brasil usando "
    "PRIORITARIAMENTE o CONTEXTO fornecido. Se o contexto não cobrir a pergunta, "
    "diga isso claramente e então responda com seu conhecimento geral, avisando "
    "que não veio da base. Seja objetivo, use passos e exemplos quando útil."
)


def _colecao():
    cliente = chromadb.PersistentClient(path=str(config.CAMINHO_CHROMA))
    return cliente.get_collection(config.NOME_COLECAO)


def buscar_contexto(pergunta: str, habilidade: str | None = None, k: int = config.TOP_K):
    emb = ollama.embeddings(model=config.MODELO_EMBEDDING, prompt=pergunta)["embedding"]
    filtro = {"habilidade": habilidade} if habilidade else None
    res = _colecao().query(query_embeddings=[emb], n_results=k, where=filtro)
    return list(zip(res["documents"][0], res["metadatas"][0], res["distances"][0]))


def responder(pergunta: str, habilidade: str | None = None, stream: bool = True):
    trechos = buscar_contexto(pergunta, habilidade)
    contexto = "\n\n---\n\n".join(doc for doc, _, _ in trechos)
    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPERGUNTA: {pergunta}"},
    ]
    fontes = sorted({m["arquivo"] for _, m, _ in trechos})
    if not stream:
        r = ollama.chat(model=config.MODELO_LLM, messages=mensagens)
        return r["message"]["content"], fontes
    for parte in ollama.chat(model=config.MODELO_LLM, messages=mensagens, stream=True):
        print(parte["message"]["content"], end="", flush=True)
    print()
    return None, fontes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pergunta")
    ap.add_argument("--habilidade", default=None)
    a = ap.parse_args()
    _, fontes = responder(a.pergunta, a.habilidade)
    print("\nFontes:", *fontes, sep="\n - ")
