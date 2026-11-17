"""
Módulo de Mapeamento Arquitetural e Grafo de Conhecimento do Código para F.R.Y.I.Vs.
Utiliza a estrutura de grafos gerada pelo Graphify (graph.json e NetworkX) para
permitir que a FRYIVS tenha um mapa completo da sua própria arquitetura, lembre-se de cada parte,
navegue entre componentes e identifique dependências com precisão cirúrgica.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Final
import networkx as nx

_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
_GRAPH_JSON_PATH = _RAIZ_PROJETO / "graphify-out" / "graph.json"
_GRAPH_REPORT_PATH = _RAIZ_PROJETO / "graphify-out" / "GRAPH_REPORT.md"

_CACHED_GRAPH: nx.Graph | None = None
_CACHED_MTIME: float = 0.0
_CACHED_DATA: dict[str, Any] | None = None


def _carregar_grafo() -> tuple[nx.Graph, dict[str, Any]]:
    """Carrega o grafo do Graphify em memória de forma eficiente com cache por mtime."""
    global _CACHED_GRAPH, _CACHED_MTIME, _CACHED_DATA

    if not _GRAPH_JSON_PATH.exists():
        # Tenta gerar o grafo inicial se não existir
        atualizar_mapa_codigo()

    if not _GRAPH_JSON_PATH.exists():
        raise FileNotFoundError(f"Arquivo do grafo não encontrado em: {_GRAPH_JSON_PATH}")

    mtime = _GRAPH_JSON_PATH.stat().st_mtime
    if _CACHED_GRAPH is not None and _CACHED_DATA is not None and mtime == _CACHED_MTIME:
        return _CACHED_GRAPH, _CACHED_DATA

    with open(_GRAPH_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    is_directed = data.get("directed", False)
    G = nx.DiGraph() if is_directed else nx.Graph()

    for node in data.get("nodes", []):
        node_id = node.get("id")
        if node_id:
            G.add_node(node_id, **node)

    links = data.get("links") or data.get("edges") or []
    for edge in links:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            G.add_edge(src, tgt, **edge)

    _CACHED_GRAPH = G
    _CACHED_DATA = data
    _CACHED_MTIME = mtime
    return G, data


def consultar_mapa_codigo(termo: str, limite: int = 5) -> str:
    """
    Pesquisa no mapa mental do código (grafo de conhecimento) funções, classes, arquivos, rotas e módulos.
    Retorna onde cada parte está localizada (arquivo e linha), o que faz e quais outros componentes ela chama ou é chamada.
    """
    if not termo or not termo.strip():
        return "Senhor, informe o termo, função ou módulo que deseja consultar no mapa do código."

    try:
        G, data = _carregar_grafo()
    except Exception as e:
        return f"Senhor, não foi possível carregar o mapa do código: {e}"

    termo_limpo = termo.strip().lower()
    matches: list[dict[str, Any]] = []

    for node_id, attrs in G.nodes(data=True):
        label = str(attrs.get("label", "")).lower()
        norm_label = str(attrs.get("norm_label", "")).lower()
        source_file = str(attrs.get("source_file", "")).lower()

        score = 0
        if termo_limpo == label or termo_limpo == norm_label or termo_limpo == node_id.lower():
            score = 100
        elif termo_limpo in label or termo_limpo in norm_label:
            score = 50
        elif termo_limpo in source_file:
            score = 25

        if score > 0:
            matches.append({"id": node_id, "score": score, "attrs": attrs})

    if not matches:
        return (
            f"Senhor, não localizei nenhuma função, classe ou módulo correspondente a '{termo}' no mapa do código. "
            "Você pode tentar um termo correlato ou solicitar uma atualização com 'atualizar_mapa_codigo'."
        )

    matches.sort(key=lambda m: (-m["score"], len(m["id"])))
    selecionados = matches[:max(1, min(limite, 10))]

    linhas: list[str] = [
        f"🗺️ **Mapa Arquitetural — Consulta por '{termo}' ({len(matches)} encontrado(s)):**\n"
    ]

    for item in selecionados:
        attrs = item["attrs"]
        node_id = item["id"]
        label = attrs.get("label", node_id)
        src_file = attrs.get("source_file", "desconhecido")
        src_loc = attrs.get("source_location", "N/A")
        tipo = attrs.get("file_type", "código")
        comm = attrs.get("community", "N/A")

        vizinhos = list(G.neighbors(node_id))
        qtd_conexoes = len(vizinhos)
        exemplos_conexoes = [G.nodes[v].get("label", v) for v in vizinhos[:4]]
        str_conexoes = ", ".join(f"`{c}`" for c in exemplos_conexoes) if exemplos_conexoes else "nenhuma direta"

        linhas.append(
            f"• **`{label}`** (em `{src_file}:{src_loc}`)\n"
            f"  - Tipo: {tipo} | Comunidade: #{comm} | Conexões: {qtd_conexoes}\n"
            f"  - Conectado a: {str_conexoes}"
        )

    return "\n".join(linhas)


def explicar_modulo_grafo(modulo_ou_funcao: str) -> str:
    """
    Explica em detalhes a anatomia de um componente ou módulo específico no grafo,
    mostrando todas as suas dependências diretas de entrada e saída.
    """
    if not modulo_ou_funcao or not modulo_ou_funcao.strip():
        return "Senhor, informe o nome do módulo ou função que deseja analisar."

    try:
        G, _ = _carregar_grafo()
    except Exception as e:
        return f"Senhor, não foi possível acessar o grafo de componentes: {e}"

    termo = modulo_ou_funcao.strip().lower()
    alvo_id = None
    melhor_attrs = None

    for node_id, attrs in G.nodes(data=True):
        if termo in (node_id.lower(), str(attrs.get("label", "")).lower(), str(attrs.get("norm_label", "")).lower()):
            alvo_id = node_id
            melhor_attrs = attrs
            break

    if not alvo_id:
        return f"Senhor, o componente '{modulo_ou_funcao}' não foi encontrado no mapa do sistema."

    label = melhor_attrs.get("label", alvo_id)
    source_file = melhor_attrs.get("source_file", "desconhecido")
    source_loc = melhor_attrs.get("source_location", "")
    comm = melhor_attrs.get("community", "N/A")

    vizinhos = list(G.neighbors(alvo_id))
    detalhes_conexoes = []
    for v in vizinhos[:8]:
        v_label = G.nodes[v].get("label", v)
        v_file = G.nodes[v].get("source_file", "")
        detalhes_conexoes.append(f"  - `{v_label}` ({v_file})")

    resp = [
        f"🔍 **Análise do Componente `{label}`:**",
        f"- Arquivo: `{source_file}` ({source_loc})",
        f"- Subconjunto / Comunidade: #{comm}",
        f"- Total de Conexões Diretas: {len(vizinhos)}",
    ]
    if detalhes_conexoes:
        resp.append("- Vínculos estruturais diretos:")
        resp.extend(detalhes_conexoes)
        if len(vizinhos) > 8:
            resp.append(f"  - ... e mais {len(vizinhos) - 8} conexões adicionais.")

    return "\n".join(resp)


def caminho_entre_componentes(origem: str, destino: str) -> str:
    """
    Identifica o caminho mais curto de chamadas, referências ou dependências entre dois componentes
    do sistema FRYIVS (ex: de 'server' até 'ask_fryvis' ou 'whisper').
    """
    if not origem or not destino:
        return "Senhor, informe tanto a origem quanto o destino para traçar a rota no grafo."

    try:
        G, _ = _carregar_grafo()
    except Exception as e:
        return f"Senhor, erro ao carregar grafo arquitetural: {e}"

    def encontrar_no(nome: str) -> str | None:
        nome_l = nome.strip().lower()
        for nid, attrs in G.nodes(data=True):
            if nome_l in (nid.lower(), str(attrs.get("label", "")).lower(), str(attrs.get("norm_label", "")).lower()):
                return nid
        return None

    id_origem = encontrar_no(origem)
    id_destino = encontrar_no(destino)

    if not id_origem:
        return f"Senhor, componente de origem '{origem}' não foi localizado no mapa."
    if not id_destino:
        return f"Senhor, componente de destino '{destino}' não foi localizado no mapa."

    try:
        caminho = nx.shortest_path(G, source=id_origem, target=id_destino)
        formatado = [f"`{G.nodes[n].get('label', n)}`" for n in caminho]
        return (
            f"📍 **Rota Arquitetural entre '{origem}' e '{destino}':**\n"
            f"{' ➔ '.join(formatado)}\n"
            f"(Distância estrutural: {len(caminho) - 1} salto(s))."
        )
    except nx.NetworkXNoPath:
        return f"Senhor, não existe conexão direta ou indireta mapeada entre '{origem}' e '{destino}'."
    except Exception as e:
        return f"Erro ao traçar rota: {e}"


def resumo_arquitetura_sistema() -> str:
    """
    Retorna uma visão panorâmica e macroscópica de toda a arquitetura da F.R.Y.I.Vs,
    incluindo seus núcleos principais (God Nodes), subsistemas e total de nós/arestas mapeados.
    """
    try:
        G, data = _carregar_grafo()
    except Exception as e:
        return f"Senhor, erro ao carregar resumo do sistema: {e}"

    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()

    # Identificar God Nodes (nós com maior grau de conexão)
    graus = sorted(G.degree, key=lambda x: x[1], reverse=True)[:6]
    god_nodes_str = []
    for nid, d in graus:
        label = G.nodes[nid].get("label", nid)
        src = G.nodes[nid].get("source_file", "")
        god_nodes_str.append(f"  1. `{label}` ({d} conexões) — em `{src}`")

    # Arquivos mapeados
    arquivos = set(attrs.get("source_file", "") for _, attrs in G.nodes(data=True) if attrs.get("source_file"))

    return (
        f"🏛️ **Arquitetura Geral da F.R.Y.I.Vs (Mapa Mental Graphify):**\n"
        f"- Total de Elementos Mapeados: {num_nodes} componentes (funções, classes, rotas)\n"
        f"- Relações Estruturais: {num_edges} conexões mapeadas\n"
        f"- Módulos/Arquivos Fontes: {len(arquivos)} arquivos do sistema\n\n"
        f"⭐ **Núcleos Centrais do Sistema (God Nodes):**\n"
        + "\n".join(god_nodes_str) + "\n\n"
        f"💡 Você pode consultar detalhes de qualquer parte com a skill `consultar_mapa_codigo` "
        f"ou visualizar o grafo interativo completo em `http://127.0.0.1:8000/graph`."
    )


def atualizar_mapa_codigo() -> str:
    """
    Executa a reindexação automática do grafo arquitetural da FRYIVS via Graphify,
    mantendo a memória viva de cada parte do código atualizada.
    """
    python_exe = str(_RAIZ_PROJETO / "venv" / "Scripts" / "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable

    try:
        res = subprocess.run(
            [python_exe, "-m", "graphify", "extract", ".", "--code-only"],
            cwd=str(_RAIZ_PROJETO),
            capture_output=True,
            text=True,
            timeout=120
        )
        # Exporta também o HTML visualizador
        subprocess.run(
            [python_exe, "-m", "graphify", "export", "html"],
            cwd=str(_RAIZ_PROJETO),
            capture_output=True,
            text=True,
            timeout=30
        )
        global _CACHED_GRAPH, _CACHED_DATA, _CACHED_MTIME
        _CACHED_GRAPH = None
        _CACHED_DATA = None
        _CACHED_MTIME = 0.0

        return "Senhor, o mapa mental da arquitetura e código da FRYIVS foi reindexado e atualizado com sucesso."
    except Exception as e:
        return f"Senhor, ocorreu uma falha ao atualizar o mapa do código: {e}"


# ==============================================================================
# Esquemas OpenAPI / JSON Schema para registro nas ferramentas da FRYIVS
# ==============================================================================

CODE_GRAPH_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_mapa_codigo",
            "description": (
                "Consulta o mapa mental e arquitetural da FRYIVS (Graphify) para localizar onde qualquer "
                "função, classe, arquivo, rota, variável ou módulo do projeto está definido e a quais outras partes ele se conecta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {
                        "type": "string",
                        "description": "Nome da função, classe, módulo ou conceito a procurar no código (ex: 'ask_fryvis', 'whisper', 'memory', 'server', 'open_app', 'router')."
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Quantidade máxima de resultados a retornar (padrão: 5)."
                    }
                },
                "required": ["termo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explicar_modulo_grafo",
            "description": (
                "Explica em detalhes a anatomia de um componente específico do sistema no grafo de conhecimento, "
                "apresentando suas dependências de entrada e saída."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "modulo_ou_funcao": {
                        "type": "string",
                        "description": "Nome exato ou aproximado do módulo, função ou classe (ex: 'execute_skill', 'ask_fryvis', 'salvar_memoria')."
                    }
                },
                "required": ["modulo_ou_funcao"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "caminho_entre_componentes",
            "description": (
                "Identifica o caminho ou fluxo de chamadas/dependências mais curto entre duas partes distintas do sistema FRYIVS."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origem": {
                        "type": "string",
                        "description": "Componente inicial (ex: 'server', 'stt', 'websocket')."
                    },
                    "destino": {
                        "type": "string",
                        "description": "Componente final (ex: 'llm', 'tts', 'chroma')."
                    }
                },
                "required": ["origem", "destino"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "resumo_arquitetura_sistema",
            "description": (
                "Apresenta uma visão panorâmica de toda a estrutura arquitetural da FRYIVS, "
                "incluindo os principais componentes centrais (God Nodes) e métricas do grafo de conhecimento."
            ),
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "atualizar_mapa_codigo",
            "description": (
                "Reindexa e atualiza o grafo de conhecimento arquitetural do projeto após mudanças ou adições de código."
            ),
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
