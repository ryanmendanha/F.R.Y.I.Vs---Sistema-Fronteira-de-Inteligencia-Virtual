"""
Módulo de Cache de Respostas Pré-indexadas da F.R.Y.I.Vs.

Permite resposta instantânea (<10ms) para 66 perguntas estáticas e frequentes
(identidade, voz, capacidades, office, web, segurança, ajuda, técnica)
sem necessidade de chamada ao LLM (Ollama/Gemini).
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np

_RAIZ_FRYIVS = Path(__file__).resolve().parent.parent
_CACHE_FILE = _RAIZ_FRYIVS / "data" / "respostas_cache.json"

_SIMILARIDADE_MINIMA_PADRAO = 0.82

_CACHE_LOCK = threading.Lock()
_DADOS_CACHE: dict[str, Any] | None = None
_EMBEDDINGS_ARRAY: np.ndarray | None = None
_EF_MODEL = None


def normalizar_chave(texto: str) -> str:
    """Normaliza texto: minúsculas, remove pontuação, acentuação e espaços extras."""
    if not texto:
        return ""
    t = texto.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def _obter_ef():
    """Retorna instância singleton do embedding function do ChromaDB."""
    global _EF_MODEL
    if _EF_MODEL is None:
        import chromadb.utils.embedding_functions as ef
        _EF_MODEL = ef.DefaultEmbeddingFunction()
    return _EF_MODEL


def carregar_cache(forcar_recarga: bool = False) -> dict[str, Any] | None:
    """Carrega dados e matriz de embeddings do cache em memória."""
    global _DADOS_CACHE, _EMBEDDINGS_ARRAY
    with _CACHE_LOCK:
        if _DADOS_CACHE is not None and not forcar_recarga:
            return _DADOS_CACHE

        if not _CACHE_FILE.exists():
            return None

        try:
            dados = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            itens = dados.get("itens", [])
            if itens:
                embs = [item["embedding"] for item in itens]
                arr = np.array(embs, dtype=np.float32)
                # Garante norma unitária
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                _EMBEDDINGS_ARRAY = arr / (norms + 1e-9)
            else:
                _EMBEDDINGS_ARRAY = np.empty((0, 384), dtype=np.float32)

            _DADOS_CACHE = dados
            return _DADOS_CACHE
        except Exception as e:
            print(f"[RespostasCache] Erro ao carregar cache: {e}")
            return None


def eh_consulta_dinamica_ou_comando(texto_norm: str) -> bool:
    """
    Retorna True se o texto for um comando de ação direto ou solicitação
    de informação dinâmica do sistema (hora, data, bateria, CPU, clima, etc.),
    garantindo que NUNCA seja interceptado pelo cache estático de respostas.
    """
    if not texto_norm:
        return False

    # 1. Consulta dinâmica de hora e data (deve executar a skill obter_hora_data)
    padroes_hora_data = [
        r"\bque horas?\b",
        r"\bque dia\b",
        r"\bqual (?:e )?(?:a )?hora\b",
        r"\bqual (?:e )?(?:a )?data\b",
        r"\bhoras sao\b",
        r"\bhorario atual\b",
        r"\bhora atual\b",
        r"\bdata atual\b",
        r"\bdata de hoje\b",
        r"\bdia de hoje\b",
        r"\bdia e hoje\b",
        r"\bdia da semana\b",
        r"\bem que dia\b",
        r"\b(?:diga|fale|mostre|informa|informe|passe|dizer|falar|saber) (?:as |a )?(?:horas?|data|dia)\b",
        r"\bme (?:diga|fale|mostre|informa|informe|passe) (?:as |a )?(?:horas?|data|dia)\b",
    ]
    for p in padroes_hora_data:
        if re.search(p, texto_norm):
            return True

    # 2. Consulta dinâmica de status, desempenho, bateria, CPU e cotação
    padroes_status = [
        r"\bcomo esta a cpu\b",
        r"\buso de (?:cpu|memoria|disco|ram)\b",
        r"\bstatus da bateria\b",
        r"\bnivel da bateria\b",
        r"\bporcentagem da bateria\b",
        r"\bstatus do (?:sistema|pc|computador)\b",
        r"\bcotacao\b",
        r"\bclima\b",
        r"\btemperatura\b",
        r"\bprevisao do tempo\b",
        r"\bcomo esta o tempo\b",
        r"\bqual o tempo\b",
    ]
    for p in padroes_status:
        if re.search(p, texto_norm):
            return True

    # 3. Comandos com verbos de ação imperativos diretos (devem ir para o roteador de skills)
    palavras = texto_norm.split()
    if palavras and palavras[0] in {
        "abra", "abre", "feche", "fecha", "minimize", "minimiza", "maximize", "maximiza",
        "crie", "cria", "edite", "edita", "bloqueie", "bloqueia", "bloquear", "trave", "trava",
        "aumente", "aumenta", "diminua", "diminui", "silencie", "silencia", "mute", "muta",
        "pesquise", "pesquisa", "procure", "procura", "busque", "busca", "baixe", "baixa",
        "salve", "salva", "liste", "lista", "limpe", "limpa", "copie", "copia", "mova", "move",
        "delete", "deleta", "toque", "toca", "execute", "executa", "faca", "faz", "tire", "tira",
        "inicie", "inicia", "adicione", "adiciona", "remova", "remove", "role", "rola",
        "clique", "clica", "leia", "le", "gere", "gera", "monte", "monta", "escreva", "escreve",
        "mostre", "mostra", "navegue", "navega", "acesse", "acessa", "digite", "digita",
        "pressione", "pressiona", "aperte", "aperta", "foca", "foque", "agende", "agenda",
        "consulte", "consulta", "analise", "analisa", "atualize", "atualiza", "substitua", "substitui"
    }:
        return True

    # 4. Pedidos educados ("pode abrir a calculadora", "pode fazer uma planilha no excel de despesas")
    # que especificam um alvo/complemento além das perguntas genéricas de capacidade
    if re.search(
        r"^(?:pode|poderia|consegue|tem como) (?:me )?(?:abrir|fechar|criar|fazer|gerar|montar|editar|"
        r"adicionar|remover|pesquisar|buscar|procurar|tocar|tirar|capturar|listar|mostrar|ler|escrever|"
        r"digitar|rolar|clicar|mutar|silenciar|bloquear)\b",
        texto_norm,
    ):
        dados = carregar_cache()
        lookup_exato = (dados or {}).get("lookup_exato", {})
        if texto_norm not in lookup_exato:
            return True

    return False


def buscar_resposta_cache(
    texto: str,
    threshold: float = _SIMILARIDADE_MINIMA_PADRAO
) -> dict[str, Any] | None:
    """
    Busca se a mensagem do usuário corresponde a uma resposta pré-indexada.

    1. Primeiro verifica casamento exato por texto normalizado (0ms).
    2. Se não houver casamento exato, calcula similaridade de cosseno via embeddings.
    3. Retorna dict com {"id", "resposta", "score", "match_type", "pergunta_referencia"}
       ou None se a maior similaridade for inferior a threshold.
    """
    if not texto or not texto.strip():
        return None

    texto_norm = normalizar_chave(texto)
    if not texto_norm:
        return None

    prefixos = r"^(?:por favor|por gentileza|pfv|ei|ola|oi|fryivs|frives|fraives|\s+)+"
    sufixos = r"(?:\s+|por favor|por gentileza|pfv|ai|pra mim|para mim)+$"
    t_limpo = re.sub(prefixos, "", texto_norm).strip()
    t_limpo = re.sub(sufixos, "", t_limpo).strip()

    # Proteção estrita: nunca interceptar comandos de ação ou consultas dinâmicas de sistema/tempo
    if eh_consulta_dinamica_ou_comando(texto_norm) or (t_limpo and eh_consulta_dinamica_ou_comando(t_limpo)):
        return None

    dados = carregar_cache()
    if not dados:
        return None

    # 1. Casamento exato por dicionário
    lookup_exato = dados.get("lookup_exato", {})
    if texto_norm in lookup_exato:
        return {
            "id": "exato",
            "resposta": lookup_exato[texto_norm],
            "score": 1.0,
            "match_type": "exato",
            "pergunta_referencia": texto_norm,
        }

    if t_limpo and t_limpo in lookup_exato:
        return {
            "id": "exato",
            "resposta": lookup_exato[t_limpo],
            "score": 0.99,
            "match_type": "exato_sem_cortesia",
            "pergunta_referencia": t_limpo,
        }

    # 2. Busca semântica por similaridade de cosseno
    if _EMBEDDINGS_ARRAY is None or len(_EMBEDDINGS_ARRAY) == 0:
        return None

    try:
        ef_model = _obter_ef()
        q_raw = ef_model([texto])[0]
        q_arr = np.array(q_raw, dtype=np.float32)
        norm_q = np.linalg.norm(q_arr)
        if norm_q > 0:
            q_arr = q_arr / norm_q

        # Produto interno = cosseno (vetores pré-normalizados)
        sims = _EMBEDDINGS_ARRAY @ q_arr
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score >= threshold:
            item = dados["itens"][best_idx]
            return {
                "id": item.get("id", ""),
                "resposta": item["resposta"],
                "score": round(best_score, 4),
                "match_type": "semantico",
                "pergunta_referencia": item["pergunta"],
            }
    except Exception as e:
        print(f"[RespostasCache] Erro na busca semântica: {e}")

    return None
