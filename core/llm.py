"""
Módulo de interação com o modelo de linguagem (LLM via Ollama) para F.R.Y.I.Vs.
Integra busca semântica de skills via ChromaDB (SkillRouter), suporte a ferramentas e histórico.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Final
from dotenv import load_dotenv

from core.skill_router import get_skill_router
from skills import ALL_SKILL_SCHEMAS, execute_skill
from core.gemini_client import ask_gemini, is_gemini_configured
from core.gptcache_manager import get_cached_response, cache_response

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
    "whatsapp", "spotify", "chrome", "edge", "print", "screenshot",
    "xlsx", "xls", "docx", "doc", "pdf", "txt", "csv", "json", "xml", "py",
    "planilha", "word", "excel", "powerpoint", "arquivo", "pasta", "documento"
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
    "qual o significado de fryvis", "sobre voce", "sua origem", "sua criacao"
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
    "volume", "janela", "programa", "listar",
    "inicia", "inici", "rodar", "roda", "rode",
    "lanca", "lance", "aciona", "execut", "execu",
    "start", "open", "launch",
    "notepad", "chrome", "edge", "firefox", "spotify",
    "discord", "steam", "calc", "explorer", "cmd", "powershell",
    "terminal", "vscode", "code", "word", "excel", "paint", "taskmgr",
    "hora", "horas", "data", "tempo", "clima", "google", "youtube", "print",
    "adicion", "remov", "edit", "cliqu", "clic", "leia", "ler", "crie", "criar", "pesquis",
    "busqu", "busca", "procur", "naveg", "acess", "entr",
    "link", "site", "pagina", "rolar", "role", "volte", "voltar", "desca", "suba",
    "primeiro", "segundo", "terceiro", "quarto", "quinto", "video", "aba", "resultado",
    "planilha", "documento", "arquivo", "pasta", "agend", "mapa", "grafo", "http", "www",
)


def _is_conversational(text: str) -> bool:
    """Detecta se o texto é uma saudação / mensagem conversacional sem comando de sistema."""
    normalized = _normalize(text.strip())
    clean_norm = re.sub(r"[^\w\s]", " ", normalized)
    clean_norm = re.sub(r"\s+", " ", clean_norm).strip()
    if _is_asking_about_self(text) or _is_asking_about_companies(text):
        return True
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
    words = normalized.split()
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
        "primeiro", "segundo", "terceiro", "volte", "voltar", "video"
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
    """
    Extrai (nome, argumentos) de um tool_call do Ollama.
    Suporta tanto objetos com atributos (.function) quanto dicionários ({"function": ...}).
    """
    if hasattr(tool, "function"):
        func = tool.function
        name = getattr(func, "name", "") or ""
        raw_args = getattr(func, "arguments", {}) or {}
    else:
        func = tool.get("function", {}) if isinstance(tool, dict) else {}
        name = func.get("name", "") if isinstance(func, dict) else ""
        raw_args = func.get("arguments", {}) if isinstance(func, dict) else {}

    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except (json.JSONDecodeError, ValueError):
            raw_args = {}

    return name, raw_args if isinstance(raw_args, dict) else {}


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

    if not t.endswith((".", "!", "?")):
        last_punct = max(t.rfind("."), t.rfind("!"), t.rfind("?"))
        if last_punct > 20:
            t = t[:last_punct + 1].strip()
        else:
            parts = t.rsplit(" ", 1)
            if len(parts) > 1 and len(parts[0]) > 10:
                base = parts[0].rstrip(",;:")
                t = f"{base}."

    if "senhor" in t.lower():
        if not t.endswith((".", "!", "?")):
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
    Envia uma mensagem para o LLM (Ollama ou Gemini Cloud) com suporte a perfis de modelo por tokens,
    histórico, contexto, tools e failover híbrido inteligente.
    Perfis suportados:
      - 'fryvis_beta': 40 tokens (ultra-sucinto)
      - 'fryvis_1.0': 50 tokens (objetivo)
      - 'fryvis_recursive': 80 tokens (refinado)
    Provedores suportados:
      - 'hybrid': Tenta Ollama local e, se falhar ou estiver offline, usa Gemini Flash Cloud.
      - 'gemini': Usa diretamente o Gemini Cloud (Google AI Studio).
      - 'ollama': Usa estritamente o Ollama local.
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

    is_conversational = _is_conversational(prompt)
    is_asking_self = _is_asking_about_self(prompt)
    profile_data = MODEL_PROFILES.get(profile, MODEL_PROFILES[DEFAULT_PROFILE])

    if max_tokens is not None and max_tokens > 0:
        _num_predict = max_tokens
    else:
        _num_predict = profile_data["tokens"]

    if is_conversational and not tools:
        cached_resp = get_cached_response(prompt)
        if cached_resp:
            print(f"[GPTCache] Resposta recuperada instantaneamente do cache para: '{prompt[:40]}'")
            return _garantir_tratamento_honroso(cached_resp), []

    if active_provider in ("gemini", "hybrid"):
        system_inst = (CONVERSATIONAL_PROMPT if is_conversational else SYSTEM_PROMPT)
        system_inst += f"\nDiretriz de extensão obrigatória: {profile_data['prompt_instruction']}"
        if is_asking_self:
            system_inst += (
                "\nInstrução prioritária de apresentação: O usuário está perguntando sobre você. "
                "Apresente-se como F.R.Y.I.Vs e declare expressamente que seu nome significa 'Sistema Fronteira de Inteligência Virtual'. "
                "Conclua sua resposta de forma honrosa e completa, tratando sempre o usuário como 'senhor'."
            )

        if is_conversational:
            available_gemini_tools = []
        elif tools is not None:
            available_gemini_tools = tools
        elif enable_semantic_skill_routing:
            router = get_skill_router()
            available_gemini_tools = router.search_relevant_skills(prompt, top_k=4, threshold=0.50)
        else:
            available_gemini_tools = ALL_SKILL_SCHEMAS

        try:
            gemini_resp, gemini_tool_calls = ask_gemini(
                prompt=prompt,
                system_instruction=system_inst,
                context=context,
                conversation_history=conversation_history,
                max_tokens=_num_predict,
                temperature=0.2,
                tools=available_gemini_tools
            )

            if gemini_tool_calls:
                executed_tools: list[dict[str, Any]] = []
                for tool in gemini_tool_calls:
                    func_name, func_args = _extract_tool_call(tool)
                    print(f"[Gemini Primary] Executando skill: {func_name}({func_args})")
                    resultado = execute_skill(func_name, func_args)
                    print(f"[Gemini Primary] Resultado: {resultado}")
                    executed_tools.append({
                        "tool": func_name,
                        "arguments": func_args,
                        "result": resultado,
                    })

                is_web_search = any(t["tool"] == "pesquisar_informacao_web" for t in executed_tools)
                last_tool_name = executed_tools[-1]["tool"]
                last_result = executed_tools[-1]["result"]

                if not is_web_search and last_tool_name in _SKILL_RESPONSE_TEMPLATES:
                    resp_direta = _SKILL_RESPONSE_TEMPLATES[last_tool_name].format(resultado=last_result)
                    return _garantir_tratamento_honroso(resp_direta), executed_tools

                if not gemini_resp or not gemini_resp.strip() or is_web_search:
                    detalhes = "; ".join(f"{t['tool']}: {t['result']}" for t in executed_tools)
                    if is_web_search:
                        prompt_sintese = (
                            f"Pergunta original do usuário: '{prompt}'.\n"
                            f"Informações obtidas na internet: {detalhes}.\n"
                            "Responda à pergunta do usuário de forma clara, completa e refinada utilizando esses dados, "
                            "sempre tratando o usuário com o vocativo 'senhor'."
                        )
                        tok_limit = 140
                    else:
                        prompt_sintese = f"Ação executada no sistema: {detalhes}. Responda ao senhor confirmando a conclusão com honra e cortesia em português."
                        tok_limit = 60

                    try:
                        sintese, _ = ask_gemini(
                            prompt=prompt_sintese,
                            system_instruction=system_inst,
                            max_tokens=tok_limit,
                            temperature=0.3
                        )
                        if sintese and not sintese.startswith("Erro:") and not sintese.startswith("Não foi possível obter resposta"):
                            gemini_resp = sintese
                        else:
                            gemini_resp = _SKILL_RESPONSE_TEMPLATES.get(last_tool_name, "{resultado}").format(resultado=last_result)
                    except Exception:
                        gemini_resp = _SKILL_RESPONSE_TEMPLATES.get(last_tool_name, "{resultado}").format(resultado=last_result)

                return _garantir_tratamento_honroso(gemini_resp), executed_tools

            if gemini_resp and not gemini_resp.startswith("Erro:") and not gemini_resp.startswith("Não foi possível obter resposta"):
                texto_formatado = _garantir_tratamento_honroso(gemini_resp)
                cache_response(prompt, texto_formatado)
                return texto_formatado, []

            print(f"[LLM] Gemini Principal indisponível ({gemini_resp}). Realizando fallback para o motor secundário (Ollama)...")
        except Exception as e:
            print(f"[LLM] Exceção no Gemini Principal: {e}. Realizando fallback para o motor secundário (Ollama)...")

    try:
        import ollama
    except ImportError:
        return "Erro: A biblioteca 'ollama' não está instalada no ambiente, senhor.", []

    messages: list[dict[str, Any]] = [{
        "role": "system",
        "content": CONVERSATIONAL_PROMPT if is_conversational else SYSTEM_PROMPT
    }]

    messages.append({
        "role": "system",
        "content": f"Diretriz de extensão obrigatória: {profile_data['prompt_instruction']}"
    })

    if is_asking_self:
        messages.append({
            "role": "system",
            "content": (
                "Instrução prioritária de apresentação: O usuário está perguntando sobre você. "
                "Apresente-se como F.R.Y.I.Vs e declare expressamente que seu nome significa 'Sistema Fronteira de Inteligência Virtual'. "
                "Conclua sua resposta de forma honrosa e completa, tratando sempre o usuário como 'senhor'."
            )
        })

    if context:
        messages.append({
            "role": "system",
            "content": f"Memória / Contexto relevante recuperado:\n{context}"
        })

    if conversation_history:
        for msg in conversation_history[-6:]:
            messages.append(msg)

    messages.append({"role": "user", "content": prompt})

    if is_conversational:
        available_tools: list = []
    elif tools is not None:
        available_tools = tools
    elif enable_semantic_skill_routing:
        router = get_skill_router()
        available_tools = router.search_relevant_skills(prompt, top_k=4, threshold=0.50)
    else:
        available_tools = ALL_SKILL_SCHEMAS

    executed_tools: list[dict[str, Any]] = []

    if available_tools:
        _ollama_num_predict = 100
    else:
        _ollama_num_predict = _num_predict

    try:
        chat_kwargs: dict[str, Any] = {
            "model": MODEL,
            "messages": messages,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": _ollama_num_predict,
            }
        }
        if available_tools:
            chat_kwargs["tools"] = available_tools

        response = ollama.chat(**chat_kwargs)
    except Exception as e:
        err_msg = str(e)
        if is_gemini_configured():
            print(f"[LLM Fallback] Ollama indisponível ({err_msg}). Acionando fallback automático para Gemini Cloud...")
            system_inst = (CONVERSATIONAL_PROMPT if is_conversational else SYSTEM_PROMPT)
            system_inst += f"\nDiretriz de extensão obrigatória: {profile_data['prompt_instruction']}"
            if is_asking_self:
                system_inst += (
                    "\nInstrução prioritária de apresentação: O usuário está perguntando sobre você. "
                    "Apresente-se como F.R.Y.I.Vs e declare expressamente que seu nome significa 'Sistema Fronteira de Inteligência Virtual'. "
                    "Conclua sua resposta de forma honrosa e completa, tratando sempre o usuário como 'senhor'."
                )
            gemini_resp, _ = ask_gemini(
                prompt=prompt,
                system_instruction=system_inst,
                context=context,
                conversation_history=conversation_history,
                max_tokens=_num_predict,
                temperature=0.2
            )
            return _garantir_tratamento_honroso(gemini_resp), []

        if "connection refused" in err_msg.lower() or "connect" in err_msg.lower():
            return (
                "Não consegui conectar ao servidor do Ollama. "
                "Verifique se o aplicativo Ollama está aberto e rodando.",
                [],
            )
        return f"Erro ao comunicar com Ollama ({MODEL}): {err_msg}", []

    raw_message = response.message if hasattr(response, "message") else response.get("message", {})
    message_dict = _message_to_dict(raw_message)

    tool_calls = message_dict.get("tool_calls") or []

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
                        "arguments": fn_args
                    }
                }]
        except Exception:
            pass

    print(f"[LLM] tool_calls detectados: {len(tool_calls)} | tools enviadas: {[t.get('function', {}).get('name') for t in available_tools]}")

    if tool_calls:
        messages.append(message_dict)

        for tool in tool_calls:
            func_name, func_args = _extract_tool_call(tool)
            print(f"[LLM] Executando skill: {func_name}({func_args})")

            resultado = execute_skill(func_name, func_args)
            print(f"[LLM] Resultado: {resultado}")

            executed_tools.append({
                "tool": func_name,
                "arguments": func_args,
                "result": resultado,
            })

            messages.append({
                "role": "tool",
                "content": str(resultado),
            })

        _FALHA_KEYWORDS = (
            "não encontrada no registro", "erro ao executar", "erro:", "exception",
            "falha ao criar", "falha ao editar"
        )
        falhas = [
            str(t.get("result", ""))
            for t in executed_tools
            if any(kw in str(t.get("result", "")).lower() for kw in _FALHA_KEYWORDS)
        ]

        if falhas:
            return f"Não foi possível concluir o comando: {'; '.join(falhas)}, senhor.", executed_tools

        template = _SKILL_RESPONSE_TEMPLATES.get(func_name)
        if template:
            resp_final = template.format(resultado=resultado)
        else:
            resp_final = f"Protocolo executado com sucesso, senhor. {resultado}"

        print(f"[LLM] Resposta gerada por template local (sem 2ª chamada LLM): '{func_name}'")
        return _garantir_tratamento_honroso(resp_final), executed_tools

    raw_resp = (message_dict.get("content", "") or "").strip()
    texto_final = _garantir_tratamento_honroso(raw_resp) if raw_resp else "Às suas ordens, senhor."
    cache_response(prompt, texto_final)
    return texto_final, []