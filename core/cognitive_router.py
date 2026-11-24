"""
Roteador Cognitivo Dual-Process (System 1 / System 2) da F.R.Y.I.Vs.

Classifica solicitações em:
- `system1` (arco reflexo rápido < 1s): saudações, perguntas conversacionais curtas,
  comandos simples de etapa única (hora, volume, abrir app, status/bateria/cpu/ram).
- `system2` (deliberativo multi-etapa): comandos encadeados com múltiplas intenções/tools
  (ex.: "pesquise X e crie uma planilha com Y"), análises complexas, comparações,
  planejamentos e delegações compostas.

Também corrige o bug legado de comandos curtos ("bateria", "status", "cpu", "ram",
"n8n", "hermes", "agentes") que antes eram classificados como conversacionais e
perdiam acesso às ferramentas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final, Literal

CognitiveMode = Literal["system1", "system2"]

PROFILE_SYSTEM1_TOKENS: Final[dict[str, int]] = {
    "fryvis_beta": 40,
    "fryvis_1.0": 50,
    "fryvis_recursive": 80,
}

PROFILE_SYSTEM2_TOKENS: Final[dict[str, int]] = {
    "fryvis_beta": 350,
    "fryvis_1.0": 500,
    "fryvis_recursive": 800,
}

# Comandos curtos (1-2 palavras) que SEMPRE precisam de acesso a ferramentas/skills
SHORT_COMMAND_KEYWORDS: Final[frozenset[str]] = frozenset({
    "bateria", "status", "cpu", "ram", "disco", "memoria", "telemetria", "sistema",
    "n8n", "hermes", "agentes", "agente", "workflows", "workflow", "missoes", "missao",
    "hora", "horas", "data", "clima", "tempo", "dolar", "bitcoin", "cotacao",
    "volume", "mutar", "desmutar", "silenciar", "print", "screenshot", "captura",
    "janelas", "janela", "bloquear", "bloqueia", "desbloquear",
    "planilha", "excel", "word", "documento", "arquivo", "arquivos", "pasta",
    "chrome", "edge", "firefox", "notepad", "calculadora", "calc", "spotify", "youtube",
    "terminal", "cmd", "powershell", "vscode", "code", "explorer", "paint", "taskmgr",
    "agenda", "agendamentos", "agendamento", "lembretes", "lembrete", "webhook",
    "whatsapp", "email", "emails", "gmail", "slack", "telegram",
    "grafo", "mapa", "arquitetura", "codigo",
})

# Tokens/radicais de ação que impedem classificação conversacional
ACTION_COMMAND_TOKENS: Final[tuple[str, ...]] = (
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
    "bateria", "status", "cpu", "ram", "disco", "telemetria",
    "n8n", "hermes", "agente", "workflow", "webhook", "deleg", "envi", "mand", "notifi",
    "cancel", "relatorio", "whatsapp", "email", "gmail", "slack", "telegram",
)

CONVERSATIONAL_KEYWORDS: Final[frozenset[str]] = frozenset({
    "oi", "ola", "hey", "ei", "bom dia", "boa tarde", "boa noite",
    "como vai", "tudo bem", "tudo bom", "tudo certo", "tudo tranquilo",
    "como voce esta", "quem e voce", "qual seu nome", "o que voce faz",
    "quais sao suas funcoes", "me ajude", "ajuda", "help", "obrigado",
    "obrigada", "valeu", "ficou otimo", "ok", "certo", "entendido",
    "me conta uma piada", "conta uma piada", "conte uma piada", "fala uma piada",
    "tchau", "ate logo", "ate mais", "muito obrigado", "muito bem",
    "parabens", "excelente trabalho",
})

SELF_IDENTITY_PATTERNS: Final[frozenset[str]] = frozenset({
    "quem e voce", "quem e tu", "quem e fryvis", "o que e fryvis",
    "qual o seu nome", "qual e o seu nome", "qual seu nome",
    "o que voce e", "o que voce faz", "fale sobre voce", "fale de voce",
    "conte sobre voce", "me fale sobre voce", "quem te criou",
    "o que significa seu nome", "o que significa fryvis",
    "significado do seu nome", "significado de fryvis",
    "qual o significado de fryvis", "sobre voce", "sua origem", "sua criacao",
})

# Indicadores explícitos de raciocínio deliberativo / análise profunda (System 2)
_COMPLEX_ANALYSIS_PATTERNS: Final[tuple[str, ...]] = (
    r"\bcompar[ae]\w*\b",
    r"\bversus\b",
    r"\bvs\b",
    r"\bdiferencas?\s+entre\b",
    r"\banalis[ae]\w*\b",
    r"\bavali[ae]\w*\b",
    r"\bestrategi\w*\b",
    r"\bplanej\w*\b",
    r"\bplano\s+de\b",
    r"\bdetalhadamente\b",
    r"\bem\s+detalhes\b",
    r"\bprofundamente\b",
    r"\bpasso\s+a\s+passo\b",
    r"\bpros\s+e\s+contras\b",
    r"\bvantagens\s+e\s+desvantagens\b",
    r"\brelatorio\b",
    r"\bdiagnostico\b",
    r"\bauditori\w*\b",
    r"\botimiz\w*\b",
    r"\brefator\w*\b",
    r"\bsintetiz\w*\b",
    r"\bcorrelacion\w*\b",
    r"\bcomo\s+implementar\b",
    r"\bexplique\s+como\s+funciona\b",
    r"\bcrie\s+um\s+plano\b",
    r"\belabor[ae]\w*\b",
    r"\bredij\w*\b",
    r"\binvestig\w*\b",
    r"\barquitetura\b",
    r"\bbenchmark\b",
)

# Conectores que encadeiam etapas sequenciais / dependentes
_SEQUENTIAL_CONNECTOR_RE = re.compile(
    r"\b(?:e\s+depois|e\s+em\s+seguida|e\s+entao|depois|em\s+seguida|entao|apos\s+isso|por\s+fim|alem\s+disso|e\s+tambem)\b|;|->"
)

_CLAUSE_SPLIT_RE = re.compile(
    r"\b(?:e\s+depois|e\s+em\s+seguida|e\s+entao|depois|em\s+seguida|entao|apos\s+isso|por\s+fim|alem\s+disso|e\s+tambem|e)\b|;|,|->"
)

# Domínios funcionais para contar intenções distintas em comandos compostos
_DOMAIN_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    "web_search": (
        "pesquis", "busqu", "busca", "procur", "cotac", "consult", "dolar",
        "bitcoin", "noticia", "internet", "google", "wikipedia",
    ),
    "office_doc": (
        "planilha", "excel", "word", "documento", "relatorio", "tabela",
        "apresentacao", "pdf", "csv", "coluna", "aba", "celula", "paragrafo",
    ),
    "create_edit": (
        "crie", "criar", "gere", "gerar", "mont", "elabore", "redija",
        "adicione", "adicion", "edite", "editar", "atualize", "exporte", "salve",
    ),
    "external_comms": (
        "envie", "enviar", "mande", "mandar", "dispare", "notifi",
        "whatsapp", "email", "gmail", "slack", "telegram", "webhook", "n8n", "workflow",
    ),
    "agents": (
        "hermes", "deleg", "subagente", "agentes", "missao", "pesquisador",
        "engenheiro", "analista", "sentinela",
    ),
    "desktop_os": (
        "abr", "fech", "minim", "maxim", "digit", "cliqu", "clic",
        "volume", "screenshot", "print", "janela", "bloquear", "chrome", "edge",
        "notepad", "spotify", "youtube", "naveg", "acess",
    ),
    "telemetry": (
        "bateria", "status", "cpu", "ram", "disco", "memoria", "telemetria",
    ),
    "code_graph": (
        "codigo", "arquitetura", "grafo", "modulo", "funcao", "refator", "audit", "debug",
    ),
}

# Padrões de comando composto em 1 única tool (ex.: "abra o chrome e pesquise X" -> pesquisar_google)
_SINGLE_TOOL_BROWSER_IDIOM_RE = re.compile(
    r"\b(?:abr\w*|inici\w*)\s+(?:o\s+|a\s+)?(?:chrome|edge|navegador|browser|google|youtube)\s+e\s+(?:pesquis\w*|busqu\w*|procur\w*|toqu\w*|reproduz\w*|acess\w*)\b"
)


@dataclass(frozen=True)
class CognitiveRouteDecision:
    """Decisão de roteamento cognitivo Dual-Process para um prompt."""

    mode: CognitiveMode
    is_conversational: bool
    reason: str
    suggested_max_tokens: int
    max_steps: int
    use_agent_loop: bool
    estimated_intents: int


def normalize_text(text: str) -> str:
    """Remove acentos e converte para minúsculo."""
    return unicodedata.normalize("NFD", (text or "").lower()).encode("ascii", "ignore").decode()


def _clean_normalized(text: str) -> str:
    norm = re.sub(r"[^\w\s]", " ", normalize_text(text.strip()))
    return re.sub(r"\s+", " ", norm).strip()


def is_short_action_command(text: str) -> bool:
    """Retorna True se o texto contém comando curto de sistema/skill (ex.: 'bateria', 'status', 'cpu', 'ram', 'n8n', 'hermes')."""
    clean = _clean_normalized(text)
    if not clean:
        return False
    tokens = clean.split()
    return any(tok in SHORT_COMMAND_KEYWORDS for tok in tokens)


def _has_action_tokens(clean_norm: str) -> bool:
    tokens = clean_norm.split()
    if any(tok in SHORT_COMMAND_KEYWORDS for tok in tokens):
        return True
    for pat in ACTION_COMMAND_TOKENS:
        if any(tok.startswith(pat) for tok in tokens):
            return True
    return False


def is_conversational_prompt(text: str) -> bool:
    """
    Determina se o prompt é puramente conversacional (sem necessidade de tools).

    Garante que comandos curtos como "bateria", "status", "cpu", "ram", "n8n",
    "hermes", "agentes" NUNCA sejam marcados como conversacionais.
    """
    clean_norm = _clean_normalized(text)
    if not clean_norm:
        return True

    if any(p in clean_norm for p in SELF_IDENTITY_PATTERNS):
        return True

    # Comandos curtos e tokens de ação SEMPRE mantêm acesso às tools
    if _has_action_tokens(clean_norm):
        return False

    # Perguntas analíticas/complexas não devem perder tools por engano
    if any(re.search(pat, clean_norm) for pat in _COMPLEX_ANALYSIS_PATTERNS):
        return False

    for kw in CONVERSATIONAL_KEYWORDS:
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


def _detect_domains_in_clause(clause: str) -> set[str]:
    clean = _clean_normalized(clause)
    if not clean:
        return set()
    tokens = clean.split()
    found: set[str] = set()
    for domain, stems in _DOMAIN_PATTERNS.items():
        for stem in stems:
            if any(tok.startswith(stem) or tok == stem for tok in tokens):
                found.add(domain)
                break
    return found


def classify_cognitive_mode(
    prompt: str,
    profile: str = "fryvis_1.0",
    context: str = "",
) -> CognitiveRouteDecision:
    """
    Classifica o prompt em `system1` (reflexo rápido) ou `system2` (deliberativo multi-step).

    Regras principais:
    - Saudações, identidades, comandos simples de 1 etapa e status curtos -> `system1`.
    - Comandos encadeados com múltiplas ações/domínios (ex.: "pesquise X e crie uma planilha com Y"),
      análises complexas, comparações ou múltiplas perguntas -> `system2`.
    """
    raw = (prompt or "").strip()
    clean = _clean_normalized(raw)
    base_s1_tokens = PROFILE_SYSTEM1_TOKENS.get(profile, PROFILE_SYSTEM1_TOKENS["fryvis_1.0"])
    base_s2_tokens = PROFILE_SYSTEM2_TOKENS.get(profile, PROFILE_SYSTEM2_TOKENS["fryvis_1.0"])
    s2_max_steps = 6 if profile == "fryvis_recursive" else 4

    is_conv = is_conversational_prompt(raw)
    if not clean:
        return CognitiveRouteDecision(
            mode="system1",
            is_conversational=True,
            reason="empty_prompt",
            suggested_max_tokens=base_s1_tokens,
            max_steps=1,
            use_agent_loop=False,
            estimated_intents=0,
        )

    # 1. Saudações / identidade pura são sempre System 1 (mantém latência < 1s e perfis de tokens)
    if is_conv and raw.count("?") < 2 and len(clean.split()) < 16:
        return CognitiveRouteDecision(
            mode="system1",
            is_conversational=True,
            reason="conversational_fast_reflex",
            suggested_max_tokens=base_s1_tokens,
            max_steps=1,
            use_agent_loop=False,
            estimated_intents=1,
        )

    # 2. Analisa cláusulas e domínios para detectar encadeamento multi-etapa
    clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(normalize_text(raw)) if c and c.strip()]
    clause_domains = [_detect_domains_in_clause(c) for c in clauses]
    active_clauses = [d for d in clause_domains if d]
    all_domains: set[str] = set().union(*active_clauses) if active_clauses else set()

    has_seq_connector = bool(_SEQUENTIAL_CONNECTOR_RE.search(normalize_text(raw)))
    is_single_browser_idiom = bool(_SINGLE_TOOL_BROWSER_IDIOM_RE.search(clean)) and len(active_clauses) <= 2 and all_domains <= {"desktop_os", "web_search"}

    if len(active_clauses) >= 2 and not is_single_browser_idiom:
        distinct_across_clauses = len(all_domains) >= 2 or has_seq_connector
        # Mesmo no mesmo domínio (ex.: "abra o notepad e digite olá mundo"), 2 verbos de ação distintos -> System 2
        if distinct_across_clauses or len(active_clauses) >= 2:
            # Evita falso positivo em frase curta tipo "cpu e ram" ou "hora e data" (telemetria/consulta única)
            if not (all_domains <= {"telemetry"} and len(clean.split()) <= 5):
                if not (all(tok in ("hora", "horas", "data", "dia", "e", "qual", "que", "sao", "a", "as", "o", "atual", "hoje") for tok in clean.split())):
                    return CognitiveRouteDecision(
                        mode="system2",
                        is_conversational=False,
                        reason="multi_step_chained_command",
                        suggested_max_tokens=base_s2_tokens,
                        max_steps=s2_max_steps,
                        use_agent_loop=True,
                        estimated_intents=max(2, len(active_clauses)),
                    )

    # 3. Indicadores explícitos de análise complexa / comparação / planejamento
    if any(re.search(pat, clean) for pat in _COMPLEX_ANALYSIS_PATTERNS):
        return CognitiveRouteDecision(
            mode="system2",
            is_conversational=False,
            reason="complex_analysis_or_comparison",
            suggested_max_tokens=base_s2_tokens,
            max_steps=s2_max_steps,
            use_agent_loop=True,
            estimated_intents=max(1, len(all_domains) or 1),
        )

    # 4. Múltiplas perguntas encadeadas ou pedido longo multi-cláusula
    word_count = len(clean.split())
    if raw.count("?") >= 2 or (word_count >= 20 and len(clauses) >= 2):
        return CognitiveRouteDecision(
            mode="system2",
            is_conversational=is_conv,
            reason="multi_question_or_long_deliberative",
            suggested_max_tokens=base_s2_tokens,
            max_steps=s2_max_steps,
            use_agent_loop=True,
            estimated_intents=max(2, raw.count("?")),
        )

    # 5. Caso contrário, arco reflexo System 1 (comando único simples ou pergunta curta)
    return CognitiveRouteDecision(
        mode="system1",
        is_conversational=is_conv,
        reason="single_step_fast_reflex",
        suggested_max_tokens=base_s1_tokens,
        max_steps=2,
        use_agent_loop=False,
        estimated_intents=1,
    )


def is_system2(prompt: str, profile: str = "fryvis_1.0", context: str = "") -> bool:
    """Atalho booleano indicando se o prompt requer cognição deliberativa System 2."""
    return classify_cognitive_mode(prompt, profile=profile, context=context).mode == "system2"
