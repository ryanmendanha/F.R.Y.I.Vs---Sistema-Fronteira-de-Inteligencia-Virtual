"""Configurações centrais do RAG. Altere aqui, não nos outros scripts."""
from pathlib import Path

RAIZ_BASE = Path(__file__).resolve().parent.parent        # pasta base_conhecimento
CAMINHO_CHROMA = RAIZ_BASE / "ferramentas" / "chroma_db"  # onde o banco vetorial é salvo
NOME_COLECAO = "base_conhecimento"

MODELO_EMBEDDING = "nomic-embed-text"  # ollama pull nomic-embed-text
MODELO_LLM = "llama3.2"                # ollama pull llama3.2

TAMANHO_MAX_CHUNK = 1500   # caracteres; seções maiores são divididas
SOBREPOSICAO = 150         # caracteres repetidos entre chunks divididos
TOP_K = 5                  # trechos recuperados por pergunta

EXTENSOES = {".md", ".txt"}
PASTAS_IGNORADAS = {"chroma_db", "__pycache__", ".git", "node_modules"}
