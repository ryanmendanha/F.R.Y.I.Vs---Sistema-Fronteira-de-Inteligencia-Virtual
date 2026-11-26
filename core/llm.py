"""
Módulo de interação com o motor cognitivo (Gemini Cloud / Ollama) da F.R.Y.I.Vs.
Integra:
- Roteamento Dual-Process System 1 / System 2 (`core.cognitive_router`).
- Loop ReAct Multi-Step controlado + execução paralela + auto-correção (`core.agent_loop`).
- Busca semântica de skills via ChromaDB (`core.skill_router`).
- Proteção contra Indirect Prompt Injection (`<external_knowledge trust="untrusted_data">` fora de `role: "system"`).
- Failover híbrido completo preservando tools entre Ollama e Gemini.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Final
from dotenv import load_dotenv

from core.agent_loop import extract_tool_call, run_agent_loop
from core.cognitive_router import (
    CognitiveRouteDecision,
    classify_cognitive_mode,
    is_short_action_command,
)
from core.gemini_client import (
    UNTRUSTED_DATA_CONSTITUTION,
    ask_gemini,
    is_gemini_configured,
    wrap_external_knowledge,
)
from core.gptcache_manager import get_cached_response, cache_response
from core.skill_router import get_skill_router
from skills import ALL_SKILL_SCHEMAS, execute_skill

load_dotenv()
MODEL: Final[str] = os.getenv("OLLAMA_MODEL", "llama3.2")
LLM_PROVIDER: Final[str] = os.getenv("LLM_PROVIDER", "gemini").lower()

SYSTEM_PROMPT: Final[str] = """\
Você é F.R.Y.I.Vs (pronuncia-se Frayvis), uma assistente virtual de inteligência artificial de elite, leal, sofisticada e prestativa, similar à F.R.I.D.A.Y. e J.A.R.V.I.S.
Você serve ao seu usuário com a mais alta consideração, lealdade e honra.

REGRAS DE IDENTIDADE (APENAS QUANDO PERGUNTAREM SOBRE VOCÊ):
- Se e SOMENTE se o usuário perguntar especificamente sobre você (quem é você, qual o seu nome, o que você é, ou qual o significado da sua sigla):
  Identifique-se como F.R.Y.I.Vs, informe que seu nome significa "Sistema Fronteira de Inteligência Virtual".
- Se o usuário perguntar qual é a sua função para as empresas (ou como você pode ajudar/ser implementada em empresas):
  Responda: "Para empresas, posso ser implementada como uma forma de aumentar a eficiência de novos funcionários, posso aprender com a sua empresa e aumentar a produtividade de comunicação, senhor."
- Não mencione essa definição completa em comandos normais ou em outras perguntas gerais, apenas quando perguntarem sobre você.

REGRAS DE CONDUTA E TRATAMENTO:
- Trate SEMPRE o usuário de forma honrosa, cortês e respeitosa pelo vocativo "senhor" (ou "Senhor") em TODAS as suas respostas sem exceção.
- Expresse lealdade e prontidão (ex: "Sim, senhor.", "Às suas ordens, senhor.", "Protocolo concluído, senhor.").
- Se o usuário pedir para abrir um app, controlar o sistema ou realizar uma ação disponível nas ferramentas, utilize a ferramenta adequada disparando a function call correspondente. NUNCA responda apenas dizendo que vai abrir sem acionar a ferramenta.
- Se o usuário fizer uma pergunta geral, conversar ou pedir explicações, responda de forma completa, elegante e sem cortar frases pela metade, sempre se dirigindo ao "senhor".

DIRETRIZES FUNDAMENTAIS DE PESQUISA NA WEB:
1. PESQUISA RETORNADA NO CHAT (PADRÃO): Se o usuário pedir para pesquisar qualquer assunto, dúvida, notícia ou fato (ex: "pesquise sobre X", "quem é Y?", "qual a cotação do dólar?") SEM pedir expressamente para abrir o Chrome ou Edge:
   - NUNCA abra a janela do navegador na tela.
   - Dispare OBRIGATORIAMENTE a ferramenta `pesquisar_informacao_web`.
   - Responda trazendo o conteúdo pesquisado DIRETAMENTE no chat para o usuário, de forma completa e polida, tratando-o como 'senhor'.
2. ABERTURA E NAVEGAÇÃO COMPLETA NO NAVEGADOR (MODO CO-PILOTO WEB):
   - Se o usuário pedir para ABRIR o navegador, acessar um site/link no Chrome/Edge ou pesquisar no Chrome/Edge/YouTube (ex: "abra o chrome e pesquise X", "pesquise no chrome sobre Y", "acesse esse link do Python no Chrome", "acesse o site X"):
     Dispare OBRIGATORIAMENTE `navegar_para` (se houver URL/site conhecido do contexto ou da conversa, ex: 'https://www.python.org'), `pesquisar_google`, `pesquisar_youtube` ou `clicar_elemento_web`. O navegador permanece aberto e conectado ao controlador Selenium da FRYIVS. NUNCA diga que abriu o navegador sem chamar a ferramenta.
   - Se o usuário pedir para abrir um link/resultado, clicar em um botão/vídeo, rolar a página, voltar, avançar, atualizar ou digitar em um campo da aba aberta (ex: "abra o primeiro link", "acesse esse link", "entre no segundo resultado", "clique em X", "role para baixo", "volte a página"):
     Dispare OBRIGATORIAMENTE `clicar_elemento_web` (passando p.ex. "primeiro link", "segundo resultado" ou o texto do link), `navegar_para`, `interagir_pagina_web` (para rolar, voltar, avançar, listar links) ou `digitar_campo_web`. NUNCA diga que não consegue mexer na aba aberta.

DIRETRIZES DO MAPA MENTAL E ARQUITETURA DO SISTEMA (GRAPHIFY):
- Você possui um mapa mental arquitetural completo de toda a sua base de código e estrutura gerado pelo Graphify.
- Se o senhor perguntar sobre como você é construída, onde fica uma função, classe, rota ou módulo, como partes do código se conectam ou pedir para lembrar/explicar qualquer parte da sua estrutura:
  - Utilize as ferramentas `consultar_mapa_codigo`, `explicar_modulo_grafo`, `caminho_entre_componentes` ou `resumo_arquitetura_sistema`.
  - Responda informando com precisão os arquivos, linhas e conexões correspondentes.

MODO SUPERCOMPUTADOR (EDIÇÃO AO VIVO E CO-PILOTO EM SEGUNDO PLANO):
- Quando houver um `[Estado de Trabalho Ativo em Segundo Plano]` no contexto (planilha Excel, documento Word ou página Web ativa) e o senhor solicitar edições ou ações de continuação sem repetir o nome do arquivo/site (ex.: "adicione uma linha com...", "remova a linha...", "adicione um parágrafo...", "abra o primeiro link", "clique em...", "role para baixo", "leia a página"):
  - Utilize imediatamente o caminho ou URL do artefato ativo correspondente e dispare a ferramenta apropriada (`editar_planilha`, `editar_documento_word`, `clicar_elemento_web`, `interagir_pagina_web`, `ler_conteudo_pagina`, `digitar_campo_web`).
  - As janelas do Excel, Word e Navegador permanecem visíveis e são atualizadas em tempo real.
"""

CONVERSATIONAL_PROMPT: Final[str] = """\
Você é F.R.Y.I.Vs (pronuncia-se Frayvis), assistente pessoal de IA de elite. Responda de forma honrosa, leal, refinada e completa em português, tratando SEMPRE o usuário com o vocativo "senhor".

IDENTIDADE:
- APENAS quando o usuário perguntar especificamente sobre você (quem é você, qual seu nome, sua função ou o significado da sua sigla):
  Apresente-se como F.R.Y.I.Vs e explique que seu nome significa "Sistema Fronteira de Inteligência Virtual".
- Quando perguntarem qual a sua função para as empresas (ou como você atua em empresas):
  Responda: "Para empresas, posso ser implementada como uma forma de aumentar a eficiência de novos funcionários, posso aprender com a sua empresa e aumentar a produtividade de comunicação, senhor."
- Em saudações comuns (como "olá", "bom dia") ou outros assuntos, responda de forma agradável e prestativa sem repetir toda essa definição técnica.
- Finalize sempre seus pensamentos de forma completa, nunca interrompendo a frase no meio.
"""

MODEL_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "fryvis_beta": {
        "id": "fryvis_beta",
        "name": "Fryivs Beta",
        "tokens": 40,
        "description": "Ultra-rápido e direto (40 tokens)",
        "prompt_instruction": "Seja extremamente concisa, direta e telegráfica. Responda em no máximo 1 frase curta, senhor."
    },
    "fryvis_1.0": {
        "id": "fryvis_1.0",
        "name": "Fryivs 1.0",
        "tokens": 50,
        "description": "Objetivo e equilibrado (50 tokens)",
        "prompt_instruction": "Seja concisa, direta e objetiva. Responda em no máximo 1 a 2 frases curtas, senhor."
    },
    "fryvis_recursive": {
        "id": "fryvis_recursive",
        "name": "Fryivs Recursive 1.1",
        "tokens": 80,
        "description": "Refinado e analítico (80 tokens)",
        "prompt_instruction": "Seja refinada, elegante e concisa. Responda em no máximo 2 frases completas, senhor."
    }
}
DEFAULT_PROFILE: Final[str] = "fryvis_1.0"

_SYSTEM2_PROMPT_INSTRUCTION: Final[str] = (
    "Modo deliberativo System 2 ativo: analise todas as etapas necessárias com rigor, "
    "encadeie ferramentas quando preciso, consolide os resultados obtidos e entregue uma resposta "
    "completa, estruturada e clara ao senhor."
)

_SKILL_RESPONSE_TEMPLATES: dict[str, str] = {
    "abrir_programa":     "{resultado}",
    "listar_janelas":      "Janelas ativas detectadas, senhor:\n{resultado}",
    "focar_janela":        "Janela trazida para o primeiro plano, senhor. {resultado}",
    "minimizar_janela":   "Janela minimizada com sucesso, senhor. {resultado}",
    "maximizar_janela":   "Janela maximizada com sucesso, senhor. {resultado}",
    "fechar_janela":       "Protocolo de encerramento executado, senhor. {resultado}",
    "digitar_texto":       "Texto digitado com precisão, senhor. {resultado}",
    "pressionar_atalho":  "Atalho de teclado executado, senhor. {resultado}",
    "controlar_volume":   "Volume ajustado, senhor. {resultado}",
    "tirar_screenshot":   "Captura de tela registrada, senhor. {resultado}",
    "obter_hora_data":    "{resultado}",
    "pesquisar_google":   "{resultado}",
    "pesquisar_informacao_web": "{resultado}",
    "pesquisar_youtube":  "Reprodução iniciada no YouTube, senhor. {resultado}",
    "status_sistema":     "Telemetria do sistema obtida, senhor:\n{resultado}",
    "bloquear_tela":      "Tela bloqueada com sucesso, senhor. {resultado}",
    "navegar_para":       "Navegação web realizada com sucesso, senhor. {resultado}",
    "pesquisar_na_web":   "Pesquisa web executada, senhor. {resultado}",
    "clicar_elemento_web": "Ação de clique na web concluída, senhor. {resultado}",
    "interagir_pagina_web": "Interação na página web realizada, senhor. {resultado}",
    "digitar_campo_web":  "Campo preenchido na página web, senhor. {resultado}",
    "ler_conteudo_pagina": "Leitura da página web finalizada, senhor:\n{resultado}",
    "capturar_tela_web":  "Captura da página web concluída, senhor. {resultado}",
    "fechar_navegador":   "Navegador web encerrado, senhor. {resultado}",
    "localizar_e_clicar_imagem": "Botão visual localizado e clicado com sucesso, senhor. {resultado}",
    "ler_texto_da_tela":  "Texto extraído da tela com sucesso, senhor:\n{resultado}",
    "gerenciar_arquivos": "Operação no sistema de arquivos realizada, senhor. {resultado}",
    "consultar_planilha": "Processamento da planilha concluído, senhor. {resultado}",
    "agendar_execucao":   "Rotina agendada no sistema com sucesso, senhor. {resultado}",
    "listar_agendamentos": "Lista de tarefas agendadas, senhor:\n{resultado}",
    "enviar_alerta_webhook": "Notificação externa enviada, senhor. {resultado}",
}

_CONVERSATIONAL_KEYWORDS: frozenset[str] = frozenset({
    "oi", "ola", "hey", "ei", "bom dia", "boa tarde", "boa noite",
    "como vai", "tudo bem", "tudo bom", "tudo certo", "tudo tranquilo",
    "como voce esta", "quem e voce", "qual seu nome", "o que voce faz",
    "quais sao suas funcoes", "me ajude", "ajuda", "help", "obrigado",
    "obrigada", "valeu", "ficou otimo", "ok", "certo", "entendido",
    "me conta uma piada", "conta uma piada", "conte uma piada", "fala uma piada",
    "tchau", "ate logo", "ate mais", "muito obrigado", "muito bem",
    "parabens", "excelente trabalho",
})

_TECH_WHITELIST: frozenset[str] = frozenset({
    "ctrl", "alt", "cmd", "win", "shift", "tab", "esc", "f1", "f2", "f3", "f4", "f5",
    "f11", "f12", "del", "wt", "calc", "yt", "ps", "kill", "cd", "ls", "dir", "ip",
    "ping", "cls", "clear", "help", "code", "run", "web", "app", "pc", "cpu", "ram",
    "bateria", "status", "n8n", "hermes", "agentes", "agente", "workflow", "workflows",
    "mcp", "rag", "llm", "tts", "stt", "ocr", "sql", "api", "wsl", "ssh", "git", "npm",
    "usd", "brl", "whatsapp", "spotify", "chrome", "edge", "print", "screenshot",
    "xlsx", "xls", "docx", "doc", "pdf", "txt", "csv", "json", "xml", "py",
    "planilha", "word", "excel", "powerpoint", "arquivo", "pasta", "documento",
})


def _normalize(text: str) -> str:
    """Remove acentos e converte para minúsculo para comparações."""
    return unicodedata.normalize("NFD", text.lower()).encode("ascii", "ignore").decode()


_SELF_IDENTITY_PATTERNS: frozenset[str] = frozenset({
    "quem e voce", "quem e tu", "quem e fryvis", "o que e fryvis",
    "qual o seu nome", "qual e o seu nome", "qual seu nome",
    "o que voce e", "o que voce faz", "fale sobre voce", "fale de voce",
    "conte sobre voce", "me fale sobre voce", "quem te criou",
    "o que significa seu nome", "o que significa fryvis",
    "significado do seu nome", "significado de fryvis",
    "qual o significado de fryvis", "sobre voce", "sua origem", "sua criacao",
})


RESPOSTA_FUNCAO_EMPRESAS: Final[str] = (
    "Para empresas, posso ser implementada como uma forma de aumentar a eficiência de novos funcionários, "
    "posso aprender com a sua empresa e aumentar a produtividade de comunicação, senhor."
)


def _is_asking_about_companies(text: str) -> bool:
    """Detecta perguntas sobre a função, utilidade ou implementação da assistente para empresas."""
    norm = re.sub(r"[^\w\s]", " ", _normalize(text.strip()))
    norm = " ".join(norm.split())
    if not norm:
        return False

    if any(w in norm for w in (
        "crie", "criar", "abra", "abrir", "pesquise", "pesquisar", "procure",
        "planilha", "excel", "word", "documento", "arquivo", "pasta",
        "chrome", "edge", "youtube", "volume", "janela", "screenshot"
    )):
        return False

    tem_empresa = any(k in norm for k in (
        "empresa", "empresas", "corporativo", "corporativa", "corporacoes", "negocio", "negocios"
    ))
    if not tem_empresa:
        return False

    gatilhos_funcao = (
        "funcao", "funcoes", "papel", "serve", "servir", "utilidade", "beneficio",
        "beneficios", "ajuda", "ajudar", "auxilia", "auxiliar", "implementa",
        "implementada", "implementado", "fazer", "faz", "objetivo", "vantagem",
        "vantagens", "aplicacao", "uso", "trabalha", "atua", "atuar", "funciona"
    )
    if any(g in norm for g in gatilhos_funcao):
        return True

    if re.search(r"\b(?:para|nas|em) (?:as |uma )?empresas?\b", norm) and len(norm.split()) <= 7:
        return True

    return False


def _is_asking_about_self(text: str) -> bool:
    """Verifica se o usuário está perguntando sobre a identidade ou sigla da assistente."""
    normalized = _normalize(text.strip())
    return any(p in normalized for p in _SELF_IDENTITY_PATTERNS)


def _is_direct_time_date_query(text: str) -> bool:
    """Detecta perguntas diretas e exclusivas sobre a hora ou data atual do sistema."""
    norm = re.sub(r"[^\w\s]", " ", _normalize(text.strip()))
    norm = " ".join(norm.split())
    if not norm:
        return False
    if any(w in norm for w in (
        "agend", "alarme", "lembrete", "todo dia", "a cada", "abra", "abrir",
        "crie", "criar", "pesquis", "planilha", "word", "documento", "chrome",
        "edge", "youtube", "volume", "janela", "print", "screenshot", "clima", "tempo"
    )):
        return False
    padroes = (
        r"\bque horas\b",
        r"\bque dia\b",
        r"\bqual (?:e )?(?:a )?(?:hora|data)\b",
        r"\bhoras sao\b",
        r"\bhorario atual\b",
        r"\bhora atual\b",
        r"\bdata atual\b",
        r"\bdata de hoje\b",
        r"\bdia de hoje\b",
        r"\bdia e hoje\b",
        r"\bdia da semana\b",
        r"\bem que dia estamos\b",
        r"\b(?:diga|fale|mostre|informa|informe|passe|dizer|falar|saber) (?:as |a )?(?:horas?|data|dia)\b",
    )
    return any(re.search(p, norm) for p in padroes)


_ACTION_AND_COMMAND_TOKENS: tuple[str, ...] = (
    "abr", "fech", "minim", "maxim", "digit", "press", "screenshot",
    "volume", "janela", "programa", "listar", "liste",
    "inicia", "inici", "rodar", "roda", "rode",
    "lanca", "lance", "aciona", "execut", "execu",
    "start", "open", "launch",
    "notepad", "chrome", "edge", "firefox", "spotify",
    "discord", "steam", "calc", "explorer", "cmd", "powershell",
    "terminal", "vscode", "code", "word", "excel", "paint", "taskmgr",
    "hora", "horas", "data", "tempo", "clima", "google", "youtube", "print",
    "adicion", "remov", "edit", "cliqu", "clic", "leia", "ler", "crie", "criar",
    "gere", "gerar", "pesquis", "busqu", "busca", "procur", "naveg", "acess", "entr",
    "link", "site", "pagina", "rolar", "role", "volte", "voltar", "desca", "suba",
    "primeiro", "segundo", "terceiro", "quarto", "quinto", "video", "aba", "resultado",
    "planilha", "documento", "arquivo", "pasta", "agend", "mapa", "grafo", "http", "www",
    "bateria", "status", "cpu", "ram", "disco", "telemetria", "monitor",
    "n8n", "hermes", "agente", "agentes", "workflow", "webhook", "deleg",
)


def _is_conversational(text: str) -> bool:
    """
    Detecta se o texto é uma saudação / mensagem conversacional sem comando de sistema.
    Comandos curtos como 'bateria', 'status', 'cpu', 'ram', 'n8n', 'hermes', 'agentes'
    NUNCA são marcados como conversacionais.
    """
    normalized = _normalize(text.strip())
    clean_norm = re.sub(r"[^\w\s]", " ", normalized)
    clean_norm = re.sub(r"\s+", " ", clean_norm).strip()
    if _is_asking_about_self(text) or _is_asking_about_companies(text):
        return True
    if is_short_action_command(text):
        return False
    if any(v in clean_norm for v in _ACTION_AND_COMMAND_TOKENS):
        return False
    for kw in _CONVERSATIONAL_KEYWORDS:
        if (
            clean_norm == kw
            or clean_norm.startswith(kw + " ")
            or clean_norm.endswith(" " + kw)
            or f" {kw} " in f" {clean_norm} "
        ):
            return True
    words = clean_norm.split()
    if len(words) <= 2:
        return True
    return False


def _is_gibberish(text: str) -> bool:
    """Detecta texto aleatório / gibberish sem sentido em português."""
    text = text.strip()
    if not text:
        return True
    if len(text) > 60:
        return False
    normalized = _normalize(text)

    if any(k in normalized for k in (
        "crie", "criar", "abra", "abrir", "faca", "fazer", "pesquise", "pesquisar",
        "planilha", "word", "documento", "arquivo", "pasta", "despesa", "relatorio",
        "quanto", "quem", "qual", "como", "onde", "quando", "horas", "hora", "data",
        "link", "resultado", "site", "pagina", "role", "rolar", "clique", "clicar",
        "primeiro", "segundo", "terceiro", "volte", "voltar", "video",
        "bateria", "status", "n8n", "hermes", "agentes", "agente", "workflow",
    )):
        return False

    tokens = re.split(r"[\s\._\-/\\]+", normalized)
    for token in tokens:
        if token in _TECH_WHITELIST:
            return False

    letters = re.sub(r"[^a-z]", "", normalized)
    if not letters:
        return False
    vowels = sum(1 for c in letters if c in "aeiou")
    vowel_ratio = vowels / len(letters)
    if vowel_ratio < 0.15:
        return True

    for word in tokens:
        consonant_streak = 0
        for ch in word:
            if ch in "aeiou":
                consonant_streak = 0
            elif ch.isalpha():
                consonant_streak += 1
                if consonant_streak >= 5:
                    return True
    return False


def _extract_tool_call(tool: Any) -> tuple[str, dict[str, Any]]:
    """Extrai (nome, argumentos) de um tool_call do Ollama ou Gemini."""
    return extract_tool_call(tool)


def _message_to_dict(message: Any) -> dict[str, Any]:
    """
    Converte a mensagem de resposta do Ollama para dicionário.
    Ollama >= 0.3 retorna objetos Message; versões antigas retornam dict.
    """
    if isinstance(message, dict):
        return message
    return {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", "") or "",
        "tool_calls": getattr(message, "tool_calls", None),
    }


def _garantir_tratamento_honroso(texto: str) -> str:
    """Garante que a resposta termine com pontuação adequada e contenha sempre o vocativo honroso 'senhor'."""
    t = (texto or "").strip()
    if not t:
        return "Às suas ordens, senhor."

    t = re.sub(
        r"\b(para o senhor|ao senhor|do senhor|com o senhor|pelo senhor|senhor)\s*[,;:]?\s+senhor\b",
        r"\1",
        t,
        flags=re.IGNORECASE,
    )

    is_structured_or_data = (
        "\n" in t
        or t.endswith(("%", ")", "]", '"', "'", "`"))
        or t[-1].isdigit()
    )
    if not is_structured_or_data and not t.endswith((".", "!", "?")):
        last_punct = max(t.rfind("."), t.rfind("!"), t.rfind("?"))
        if last_punct > 20:
            t = t[:last_punct + 1].strip()
        else:
            parts = t.rsplit(" ", 1)
            if len(parts) > 1 and len(parts[0]) > 10:
                base = parts[0].rstrip(",;:")
                t = f"{base}."

    if "senhor" in t.lower():
        if not t.endswith((".", "!", "?", "`", ")")):
            return f"{t}."
        return t

    if t.endswith("?"):
        return f"{t[:-1].strip()}, senhor?"
    elif t.endswith("!"):
        return f"{t[:-1].strip()}, senhor!"
    elif t.endswith("."):
        return f"{t[:-1].strip()}, senhor."
    else:
        return f"{t}, senhor."


def _build_system_instruction(
    is_conversational: bool,
    is_asking_self: bool,
    profile_data: dict[str, Any],
    route: CognitiveRouteDecision,
) -> str:
    """Monta a instrução de sistema sem jamais incluir dados externos/RAG."""
    system_inst = CONVERSATIONAL_PROMPT if is_conversational else SYSTEM_PROMPT
    if route.mode == "system2":
        system_inst += f"\nDiretriz cognitiva: {_SYSTEM2_PROMPT_INSTRUCTION}"
    else:
        system_inst += f"\nDiretriz de extensão obrigatória: {profile_data['prompt_instruction']}"
    if is_asking_self:
        system_inst += (
            "\nInstrução prioritária de apresentação: O usuário está perguntando sobre você. "
            "Apresente-se como F.R.Y.I.Vs e declare expressamente que seu nome significa 'Sistema Fronteira de Inteligência Virtual'. "
            "Conclua sua resposta de forma honrosa e completa, tratando sempre o usuário como 'senhor'."
        )
    return system_inst


def _resolve_available_tools(
    prompt: str,
    tools: list[dict[str, Any]] | None,
    is_conversational: bool,
    enable_semantic_skill_routing: bool,
    route: CognitiveRouteDecision,
) -> list[dict[str, Any]]:
    if is_conversational:
        return []
    if tools is not None:
        return tools
    if enable_semantic_skill_routing:
        router = get_skill_router()
        if route.mode == "system2":
            return router.search_relevant_skills(prompt, top_k=8, threshold=0.55)
        return router.search_relevant_skills(prompt, top_k=4, threshold=0.50)
    return ALL_SKILL_SCHEMAS


def _make_fast_template_fn(route: CognitiveRouteDecision):
    """
    Cria callback de resposta instantânea (System 1) para uma única skill OS/sistema
    com template determinístico. Retorna None em System 2, buscas web ou múltiplas tools
    para que o loop ReAct devolva as observações ao LLM.
    """
    def _fast_template(step_tools: list[dict[str, Any]], _step_text: str) -> str | None:
        if route.mode == "system2":
            return None
        if len(step_tools) != 1:
            return None
        tool_name = step_tools[0]["tool"]
        if tool_name == "pesquisar_informacao_web":
            return None
        template = _SKILL_RESPONSE_TEMPLATES.get(tool_name)
        if not template:
            return None
        return template.format(resultado=step_tools[0]["result"])

    return _fast_template


def _build_react_followup_prompt(original_prompt: str, loop_messages: list[dict[str, Any]], allow_tools: bool) -> str:
    """Constrói prompt estruturado com as observações das ferramentas para etapas 2+ no Gemini."""
    obs_lines: list[str] = []
    correction_notes: list[str] = []
    for msg in loop_messages[1:]:
        role = msg.get("role")
        if role == "tool":
            obs_lines.append(f"- Ferramenta `{msg.get('name', 'tool')}` retornou: {msg.get('content', '')}")
        elif role == "user" and str(msg.get("content", "")).startswith("[Auto-Correção"):
            correction_notes.append(str(msg.get("content", "")))

    observations_block = "\n".join(obs_lines)
    correction_block = ("\n\n" + "\n".join(correction_notes)) if correction_notes else ""

    if allow_tools:
        directive = (
            "Com base nas observações acima, se ainda houver próxima etapa pendente ou correção "
            "necessária, chame a próxima ferramenta adequada; caso contrário, responda de forma "
            "clara, completa e polida ao senhor consolidando todos os resultados."
        )
    else:
        directive = (
            "Todas as ferramentas já foram executadas. Consolide todas as observações acima "
            "e responda diretamente ao pedido original de forma clara, completa e honrosa ao senhor."
        )

    return (
        f"Pedido original do usuário: {original_prompt}\n\n"
        f"Observações das ferramentas já executadas:\n{observations_block}"
        f"{correction_block}\n\n{directive}"
    )


def _run_gemini_with_loop(
    *,
    prompt: str,
    system_inst: str,
    context: str,
    conversation_history: list[dict[str, str]] | None,
    available_tools: list[dict[str, Any]],
    num_predict: int,
    route: CognitiveRouteDecision,
) -> tuple[str, list[dict[str, Any]]]:
    """Executa Gemini com suporte completo a System 1 fast-path e System 2 ReAct loop."""
    synth_tokens = max(num_predict, 350 if route.mode == "system2" else 160)

    def _gemini_step(loop_messages: list[dict[str, Any]], step: int, allow_tools: bool) -> tuple[str, list[dict[str, Any]]]:
        step_tools = available_tools if (allow_tools and available_tools) else None
        if step == 1:
            return ask_gemini(
                prompt=prompt,
                system_instruction=system_inst,
                context=context,
                conversation_history=conversation_history,
                max_tokens=num_predict,
                temperature=0.2,
                tools=step_tools if step_tools is not None else [],
            )

        followup_prompt = _build_react_followup_prompt(prompt, loop_messages, allow_tools=allow_tools)
        return ask_gemini(
            prompt=followup_prompt,
            system_instruction=system_inst,
            context=context,
            conversation_history=conversation_history,
            max_tokens=synth_tokens,
            temperature=0.3 if not allow_tools else 0.2,
            tools=step_tools,
        )

    result = run_agent_loop(
        prompt=prompt,
        llm_step_fn=_gemini_step,
        execute_tool_fn=execute_skill,
        max_steps=route.max_steps,
        max_wall_time_s=60.0,
        max_error_retries=1,
        max_workers=3,
        extract_tool_call_fn=_extract_tool_call,
        fast_template_fn=_make_fast_template_fn(route),
    )
    return result.response, result.executed_tools


def _parse_ollama_tool_calls(
    message_dict: dict[str, Any],
    available_tools: list[dict[str, Any]],
) -> list[Any]:
    tool_calls = list(message_dict.get("tool_calls") or [])
    content_text = (message_dict.get("content") or "").strip()
    if not tool_calls and content_text.startswith("{") and content_text.endswith("}"):
        try:
            parsed_json = json.loads(content_text)
            fn_name = parsed_json.get("name") or parsed_json.get("function")
            fn_args = parsed_json.get("parameters") or parsed_json.get("arguments") or {}
            if fn_name and any(t.get("function", {}).get("name") == fn_name for t in available_tools):
                tool_calls = [{
                    "function": {
                        "name": fn_name,
                        "arguments": fn_args,
                    }
                }]
        except Exception:
            pass
    return tool_calls


def ask_fryvis(
    prompt: str,
    context: str = "",
    tools: list[dict[str, Any]] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    enable_semantic_skill_routing: bool = True,
    profile: str = DEFAULT_PROFILE,
    max_tokens: int | None = None,
    provider: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """
    Envia uma mensagem para o motor cognitivo (Gemini Cloud ou Ollama) com:
    - Classificação Dual-Process System 1 / System 2 (`core.cognitive_router`).
    - Loop ReAct Multi-Step + ferramentas paralelas + auto-correção (`core.agent_loop`).
    - Isolamento anti-prompt-injection (`<external_knowledge trust="untrusted_data">` fora de system).
    - Failover híbrido completo preservando `tools` entre provedores.
    """
    active_provider = (provider or LLM_PROVIDER).lower()

    if _is_gibberish(prompt):
        print(f"[LLM] Gibberish detectado: '{prompt[:40]}' — retornando sem chamar LLM")
        return "Não é possível usar esse comando, senhor.", []

    from core.skill_router import eh_comando_vago_ou_perigoso
    bloqueado_seguranca, msg_seguranca = eh_comando_vago_ou_perigoso(prompt)
    if bloqueado_seguranca:
        return msg_seguranca, []

    if _is_asking_about_companies(prompt):
        return RESPOSTA_FUNCAO_EMPRESAS, []

    if tools is None and enable_semantic_skill_routing and _is_direct_time_date_query(prompt):
        resultado_hd = execute_skill("obter_hora_data", {})
        resp_hd = _SKILL_RESPONSE_TEMPLATES.get("obter_hora_data", "{resultado}").format(resultado=resultado_hd)
        return _garantir_tratamento_honroso(resp_hd), [{
            "tool": "obter_hora_data",
            "arguments": {},
            "result": resultado_hd,
        }]

    route = classify_cognitive_mode(prompt, profile=profile, context=context)
    is_conversational = _is_conversational(prompt)
    is_asking_self = _is_asking_about_self(prompt)
    profile_data = MODEL_PROFILES.get(profile, MODEL_PROFILES[DEFAULT_PROFILE])

    # Teto dinâmico de tokens: System 1 preserva perfis concisos (40/50/80); System 2 eleva para 350-800
    if max_tokens is not None and max_tokens > 0:
        _num_predict = max_tokens
    elif route.mode == "system2":
        _num_predict = route.suggested_max_tokens
    elif profile == "fryvis_recursive" and not is_conversational:
        _num_predict = 400
    else:
        _num_predict = profile_data["tokens"]

    can_use_gptcache = (
        is_conversational
        and not tools
        and route.mode == "system1"
        and not context
        and not conversation_history
    )
    if can_use_gptcache:
        cached_resp = get_cached_response(prompt)
        if cached_resp:
            print(f"[GPTCache] Resposta recuperada instantaneamente do cache para: '{prompt[:40]}'")
            return _garantir_tratamento_honroso(cached_resp), []

    system_inst = _build_system_instruction(
        is_conversational=is_conversational,
        is_asking_self=is_asking_self,
        profile_data=profile_data,
        route=route,
    )

    available_tools = _resolve_available_tools(
        prompt=prompt,
        tools=tools,
        is_conversational=is_conversational,
        enable_semantic_skill_routing=enable_semantic_skill_routing,
        route=route,
    )

    if active_provider in ("gemini", "hybrid"):
        try:
            gemini_resp, executed_tools = _run_gemini_with_loop(
                prompt=prompt,
                system_inst=system_inst,
                context=context,
                conversation_history=conversation_history,
                available_tools=available_tools,
                num_predict=_num_predict,
                route=route,
            )

            if executed_tools:
                return _garantir_tratamento_honroso(gemini_resp), executed_tools

            if (
                gemini_resp
                and not gemini_resp.startswith("Erro:")
                and not gemini_resp.startswith("Não foi possível obter resposta")
            ):
                texto_formatado = _garantir_tratamento_honroso(gemini_resp)
                if can_use_gptcache:
                    cache_response(prompt, texto_formatado)
                return texto_formatado, []

            print(f"[LLM] Gemini Principal indisponível ({gemini_resp}). Realizando fallback para o motor secundário (Ollama)...")
        except Exception as e:
            print(f"[LLM] Exceção no Gemini Principal: {e}. Realizando fallback para o motor secundário (Ollama)...")

    try:
        import ollama
    except ImportError:
        return "Erro: A biblioteca 'ollama' não está instalada no ambiente, senhor.", []

    # Construção segura de mensagens Ollama: contexto SEMPRE fora de `role: "system"`
    base_messages: list[dict[str, Any]] = [{
        "role": "system",
        "content": CONVERSATIONAL_PROMPT if is_conversational else SYSTEM_PROMPT,
    }]

    if route.mode == "system2":
        base_messages.append({
            "role": "system",
            "content": f"Diretriz cognitiva: {_SYSTEM2_PROMPT_INSTRUCTION}",
        })
    else:
        base_messages.append({
            "role": "system",
            "content": f"Diretriz de extensão obrigatória: {profile_data['prompt_instruction']}",
        })

    if is_asking_self:
        base_messages.append({
            "role": "system",
            "content": (
                "Instrução prioritária de apresentação: O usuário está perguntando sobre você. "
                "Apresente-se como F.R.Y.I.Vs e declare expressamente que seu nome significa 'Sistema Fronteira de Inteligência Virtual'. "
                "Conclua sua resposta de forma honrosa e completa, tratando sempre o usuário como 'senhor'."
            ),
        })

    wrapped_context = wrap_external_knowledge(context)
    if wrapped_context:
        base_messages.append({
            "role": "system",
            "content": UNTRUSTED_DATA_CONSTITUTION,
        })

    if conversation_history:
        for msg in conversation_history[-6:]:
            base_messages.append(msg)

    user_content = f"{wrapped_context}\n\n{prompt}" if wrapped_context else prompt
    base_messages.append({"role": "user", "content": user_content})

    # Quando há ferramentas disponíveis, eleva num_predict para >= 350 evitando truncamento de JSON
    _ollama_num_predict = max(_num_predict, 350) if available_tools else _num_predict

    def _ollama_step(
        loop_messages: list[dict[str, Any]],
        step: int,
        allow_tools: bool,
    ) -> tuple[str, list[dict[str, Any]]]:
        step_predict = (
            max(_ollama_num_predict, 350)
            if (step > 1 or route.mode == "system2" or available_tools)
            else _ollama_num_predict
        )
        chat_kwargs: dict[str, Any] = {
            "model": MODEL,
            "messages": loop_messages,
            "options": {
                "temperature": 0.2 if allow_tools else 0.3,
                "top_p": 0.9,
                "num_predict": step_predict,
            },
        }
        if allow_tools and available_tools:
            chat_kwargs["tools"] = available_tools

        response = ollama.chat(**chat_kwargs)
        raw_message = response.message if hasattr(response, "message") else response.get("message", {})
        message_dict = _message_to_dict(raw_message)
        step_tool_calls = _parse_ollama_tool_calls(message_dict, available_tools) if allow_tools else []
        print(
            f"[LLM] Ollama step {step} | mode={route.mode} | tool_calls={len(step_tool_calls)} | "
            f"tools={[t.get('function', {}).get('name') for t in available_tools]}"
        )
        return (message_dict.get("content", "") or "").strip(), step_tool_calls

    try:
        loop_result = run_agent_loop(
            prompt=prompt,
            llm_step_fn=_ollama_step,
            execute_tool_fn=execute_skill,
            max_steps=route.max_steps,
            max_wall_time_s=60.0,
            max_error_retries=1,
            max_workers=3,
            extract_tool_call_fn=_extract_tool_call,
            initial_messages=base_messages,
            fast_template_fn=_make_fast_template_fn(route),
        )
    except Exception as e:
        err_msg = str(e)
        if is_gemini_configured():
            print(f"[LLM Fallback] Ollama indisponível ({err_msg}). Acionando fallback automático para Gemini Cloud (preservando {len(available_tools)} tools)...")
            gemini_resp, gemini_tools = _run_gemini_with_loop(
                prompt=prompt,
                system_inst=system_inst,
                context=context,
                conversation_history=conversation_history,
                available_tools=available_tools,
                num_predict=_num_predict,
                route=route,
            )
            return _garantir_tratamento_honroso(gemini_resp), gemini_tools

        if "connection refused" in err_msg.lower() or "connect" in err_msg.lower():
            return (
                "Não consegui conectar ao servidor do Ollama. "
                "Verifique se o aplicativo Ollama está aberto e rodando.",
                [],
            )
        return f"Erro ao comunicar com Ollama ({MODEL}): {err_msg}", []

    if loop_result.executed_tools:
        return _garantir_tratamento_honroso(loop_result.response), loop_result.executed_tools

    raw_resp = (loop_result.response or "").strip()
    texto_final = _garantir_tratamento_honroso(raw_resp) if raw_resp else "Às suas ordens, senhor."
    if can_use_gptcache:
        cache_response(prompt, texto_final)
    return texto_final, []
