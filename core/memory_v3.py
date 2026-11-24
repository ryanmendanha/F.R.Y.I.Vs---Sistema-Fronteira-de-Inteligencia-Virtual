"""
Motor de Memória Tripartite v3, Sessões Persistentes em SQLite e Sanitizador
Anti-Prompt-Injection para F.R.Y.I.Vs.

Componentes:
1. Classificação Taxonômica Tripartite:
   - `episodic`: interações datadas com curva de decaimento temporal rápida.
   - `semantic`: fatos e preferências estáveis com deduplicação/merge (sim >= 0.88).
   - `procedural`: padrões bem-sucedidos, fluxos e receitas aprendidas.
2. Persistência SQLite (`data/sessions.db`, modo WAL, thread-safe):
   - `session_turns`: histórico ordenado de turnos por sessão (sobrevive reinícios).
   - `memory_meta`: índice temporal e de importância/acesso para ordenação real e
     ranking composto (`score = sim * 0.70 + recency_decay * 0.20 + importance * 0.10`).
3. Sanitizador de Indirect Prompt Injection (`sanitizar_conteudo_externo`):
   - Detecta e remove comentários HTML/JS ocultos, tags perigosas, ofuscação Unicode
     zero-width e diretivas clássicas de jailbreak/prompt-injection em PT/EN.
   - Isola conteúdo externo em tags `<external_knowledge trust="external_sanitized">`.
"""

from __future__ import annotations

import html
import math
import os
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Constantes de taxonomia e scoring
# ---------------------------------------------------------------------------

MEMORY_TYPE_EPISODIC: Final[str] = "episodic"
MEMORY_TYPE_SEMANTIC: Final[str] = "semantic"
MEMORY_TYPE_PROCEDURAL: Final[str] = "procedural"
VALID_MEMORY_TYPES: Final[frozenset[str]] = frozenset(
    {MEMORY_TYPE_EPISODIC, MEMORY_TYPE_SEMANTIC, MEMORY_TYPE_PROCEDURAL}
)

TRUST_VERIFIED_INTERNAL: Final[str] = "verified_internal"
TRUST_EXTERNAL_SANITIZED: Final[str] = "external_sanitized"

# Meia-vida em dias para decaimento exponencial por tipo de memória
HALF_LIFE_DAYS: Final[dict[str, float]] = {
    MEMORY_TYPE_EPISODIC: 7.0,
    MEMORY_TYPE_PROCEDURAL: 60.0,
    MEMORY_TYPE_SEMANTIC: 180.0,
}

# Pesos do score composto: sim * 0.70 + recency_decay * 0.20 + importance * 0.10
WEIGHT_SIMILARITY: Final[float] = 0.70
WEIGHT_RECENCY: Final[float] = 0.20
WEIGHT_IMPORTANCE: Final[float] = 0.10

# Limiares padrão
DEFAULT_COSINE_THRESHOLD: Final[float] = 0.65
SEMANTIC_DEDUP_MAX_DISTANCE: Final[float] = 0.12  # cosine similarity >= 0.88
EPISODIC_DEDUP_MAX_DISTANCE: Final[float] = 0.04  # cosine similarity >= 0.96
DEFAULT_MAX_SESSION_TURNS: Final[int] = 20

_RAIZ_FRYIVS: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_SESSIONS_DB_PATH: Final[Path] = _RAIZ_FRYIVS / "data" / "sessions.db"


# ---------------------------------------------------------------------------
# Normalização auxiliar
# ---------------------------------------------------------------------------

def _normalizar_ascii(texto: str) -> str:
    """Remove acentos, reduz para minúsculas e colapsa espaços."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", sem_acentos.lower()).strip()


def _extrair_fala_usuario(texto: str) -> str:
    """Extrai a fala do usuário se o registro estiver no formato 'Usuário: ... | FRYVIS: ...'."""
    m = re.match(r"^\s*usu[aá]rio\s*:\s*(.*?)(?:\s*\|\s*fryvis\s*:.*)?$", texto.strip(), re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return texto.strip()


# ---------------------------------------------------------------------------
# Filtro de comandos efêmeros / ruidosos
# ---------------------------------------------------------------------------

_EPHEMERAL_EXACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Saudações e confirmações puras
    re.compile(
        r"^(?:oi+|ola+|eae|fala|bom dia|boa tarde|boa noite|tudo bem|como vai|"
        r"ok+|okay|certo|beleza|valeu|obrigad[oa]|muito obrigad[oa]|perfeito|"
        r"entendido|sim|nao|tchau|ate logo|ate mais|legal|show|massa|blz)[!?. ]*$"
    ),
    # Consultas triviais de hora / data
    re.compile(
        r"^(?:(?:me\s+diga\s+|diga\s+|fala\s+|qual\s+(?:e\s+)?a\s+|que\s+)?"
        r"(?:horas?\s+sao|hora\s+e|horario(?:\s+atual)?|data\s+de\s+hoje|dia\s+e\s+hoje)"
        r"(?:\s+agora|\s+por\s+favor|\s+frives|\s+fryvis)?)[!?. ]*$"
    ),
    # Comandos efêmeros de volume, áudio, mídia e brilho
    re.compile(
        r"^(?:(?:por\s+favor\s+)?(?:aument[ae]|abaix[ae]|diminu[ai]|sobe|desce|coloc[ae]|ajust[ae]|defin[ae])\s+"
        r"(?:o\s+)?(?:volume|som|audio|brilho)(?:\s+(?:para|em|no|a)\s+\d+%?)?|"
        r"(?:mut[ae]r?|desmut[ae]r?|silencio|silenciar|calar|pare\s+de\s+falar|cala\s+a\s+boca|"
        r"paus[ae]r?|continu[ae]r?|play|pause|proxima\s+musica|musica\s+anterior))[!?. ]*$"
    ),
    # Comandos em inglês equivalentes
    re.compile(
        r"^(?:what\s+time\s+is\s+it|current\s+time|volume\s+(?:up|down)|mute|unmute|"
        r"hello|hi|hey|thanks|thank\s+you|bye|stop\s+talking)[!?. ]*$"
    ),
)


def eh_comando_efemero(texto: str) -> bool:
    """
    Identifica comandos efêmeros/ruidosos (ex.: 'que horas são?', 'aumente o volume',
    saudações isoladas) que não agregam valor à memória vetorial de longo prazo.
    """
    if not texto or not texto.strip():
        return True
    fala = _extrair_fala_usuario(texto)
    norm = _normalizar_ascii(fala)
    if not norm:
        return True
    # Remove vocativo inicial opcional ("frives, que horas sao?")
    norm_sem_vocativo = re.sub(r"^(?:ei\s+|hey\s+|ok\s+)?(?:frives|fryvis|fryivs|jarvis)[,\s]+", "", norm).strip()
    candidatos = (norm, norm_sem_vocativo) if norm_sem_vocativo and norm_sem_vocativo != norm else (norm,)
    for cand in candidatos:
        for pat in _EPHEMERAL_EXACT_PATTERNS:
            if pat.match(cand):
                return True
    return False


# ---------------------------------------------------------------------------
# Classificação taxonômica tripartite
# ---------------------------------------------------------------------------

_PROCEDURAL_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:sempre\s+que|quando\s+eu\s+pedir|toda\s+vez\s+que|passo\s+a\s+passo)\b"),
    re.compile(r"\b(?:workflow|fluxo\s+de\s+trabalho|procedimento|receita|playbook|pipeline|rotina)\b"),
    re.compile(r"\b(?:ao\s+(?:gerar|criar|montar|enviar|formatar|exportar)|formato\s+padrao|padrao\s+de\s+relatorio)\b"),
    re.compile(r"\b(?:como\s+(?:fazer|executar|configurar|gerar|montar)|execute\s+nessa\s+ordem|sequencia\s+de\s+passos)\b"),
    re.compile(r"\b(?:sempre\s+(?:gere|crie|use|salve|exporte|envie|formate|inclua|adote))\b"),
    re.compile(r"\b(?:template\s+de|checklist\s+de|learned\s+workflow|how\s+to\s+run)\b"),
)

_SEMANTIC_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:prefiro|preferencia|gosto\s+de|nao\s+gosto|adoro|odeio|costumo)\b"),
    re.compile(r"\b(?:meu\s+nome\s+e|me\s+chamo|eu\s+sou|trabalho\s+(?:na|no|em|como)|minha\s+empresa|meu\s+cargo)\b"),
    re.compile(r"\b(?:lembre(?:-se)?\s+(?:que|de)|anote\s+que|memorize|guarde\s+que|nunca\s+esqueca)\b"),
    re.compile(r"\b(?:idioma\s+preferido|lingua\s+nativa|codigo\s+do\s+projeto|configuracao\s+de|servidor\s+(?:fica|usa|esta))\b"),
    re.compile(r"\b(?:o\s+usuario\s+(?:prefere|usa|trabalha|fala|mora|gosta|tem)|usuario\s*:|cargo\s*:|cidade\s*:)\b"),
    re.compile(r"\b(?:projeto\s+(?:principal|usa|utiliza)|regra\s+de\s+negocio|stack\s+(?:e|usa)|porta\s*:|ip\s*:)\b"),
    re.compile(r"\b(?:user\s+prefers|my\s+name\s+is|i\s+prefer|always\s+use|fact\s*:)\b"),
)

_HIGH_IMPORTANCE_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:importante|critico|essencial|obrigatorio|prioridade|lembre(?:-se)?|memorize|nunca\s+esqueca|atualizacao)\b"),
    re.compile(r"\b(?:critical|important|remember\s+that|never\s+forget)\b"),
)


def classificar_memoria(
    texto: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, float]:
    """
    Classifica uma memória na taxonomia tripartite (`episodic`, `semantic`, `procedural`)
    e estima sua importância inicial em `[0.0, 1.0]`.
    """
    meta = metadata or {}
    tipo_explicito = str(meta.get("memory_type") or "").strip().lower()
    norm = _normalizar_ascii(texto)

    if tipo_explicito in VALID_MEMORY_TYPES:
        mem_type = tipo_explicito
        base_imp = {
            MEMORY_TYPE_PROCEDURAL: 0.78,
            MEMORY_TYPE_SEMANTIC: 0.80,
            MEMORY_TYPE_EPISODIC: 0.55,
        }[mem_type]
    else:
        proc_hits = sum(1 for p in _PROCEDURAL_CUES if p.search(norm))
        sem_hits = sum(1 for p in _SEMANTIC_CUES if p.search(norm))

        if proc_hits > 0 and proc_hits >= sem_hits:
            mem_type = MEMORY_TYPE_PROCEDURAL
            base_imp = 0.78
        elif sem_hits > 0:
            mem_type = MEMORY_TYPE_SEMANTIC
            base_imp = 0.80
        else:
            mem_type = MEMORY_TYPE_EPISODIC
            base_imp = 0.55

    if "importance" in meta and meta["importance"] is not None:
        try:
            imp = float(meta["importance"])
            return mem_type, max(0.0, min(1.0, round(imp, 4)))
        except (TypeError, ValueError):
            pass

    imp = base_imp
    if any(p.search(norm) for p in _HIGH_IMPORTANCE_CUES):
        imp += 0.15
    if len(norm) >= 120:
        imp += 0.05
    elif len(norm) < 20:
        imp -= 0.05

    return mem_type, max(0.05, min(1.0, round(imp, 4)))


# ---------------------------------------------------------------------------
# Curva de decaimento temporal e score composto
# ---------------------------------------------------------------------------

def calcular_recency_decay(
    created_at: float,
    memory_type: str = MEMORY_TYPE_EPISODIC,
    now: float | None = None,
) -> float:
    """
    Calcula fator de decaimento exponencial em `(0.0, 1.0]` baseado na idade
    da memória e na meia-vida do tipo taxonômico.
    """
    ref_now = time.time() if now is None else float(now)
    age_seconds = max(0.0, ref_now - float(created_at))
    age_days = age_seconds / 86400.0
    half_life = HALF_LIFE_DAYS.get(memory_type, HALF_LIFE_DAYS[MEMORY_TYPE_EPISODIC])
    decay = math.exp(-math.log(2.0) * age_days / max(half_life, 0.1))
    return max(0.0, min(1.0, decay))


def calcular_score_composto(
    cosine_distance: float,
    created_at: float,
    importance: float = 0.5,
    memory_type: str = MEMORY_TYPE_EPISODIC,
    now: float | None = None,
) -> float:
    """
    Calcula o score composto de relevância:
        score = sim * 0.70 + recency_decay * 0.20 + importance * 0.10
    onde `sim = clamp(1.0 - cosine_distance, 0.0, 1.0)`.
    """
    sim = max(0.0, min(1.0, 1.0 - float(cosine_distance)))
    decay = calcular_recency_decay(created_at=created_at, memory_type=memory_type, now=now)
    imp = max(0.0, min(1.0, float(importance)))
    score = (sim * WEIGHT_SIMILARITY) + (decay * WEIGHT_RECENCY) + (imp * WEIGHT_IMPORTANCE)
    return round(score, 6)


# ---------------------------------------------------------------------------
# Sanitizador Anti-Indirect-Prompt-Injection
# ---------------------------------------------------------------------------

# Caracteres invisíveis / direcionais usados para ofuscar payloads
_ZERO_WIDTH_RE: Final[re.Pattern[str]] = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]"
)

# Comentários HTML / JS e blocos ocultos
_HTML_COMMENT_RE: Final[re.Pattern[str]] = re.compile(r"<!--(.*?)-->", re.DOTALL | re.IGNORECASE)
_JS_BLOCK_COMMENT_RE: Final[re.Pattern[str]] = re.compile(r"/\*(.*?)\*/", re.DOTALL)
_SCRIPT_STYLE_RE: Final[re.Pattern[str]] = re.compile(
    r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_HIDDEN_HTML_ELEMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"<\s*([a-z0-9]+)\b[^>]*style\s*=\s*['\"][^'\"]*"
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\b|font-size\s*:\s*0)"
    r"[^'\"]*['\"][^>]*>.*?<\s*/\s*\1\s*>",
    re.DOTALL | re.IGNORECASE,
)

# Tentativas de escapar/forjar tags de isolamento de contexto
_TAG_BREAKOUT_RE: Final[re.Pattern[str]] = re.compile(
    r"<\s*/?\s*(?:external_knowledge|system|system_prompt|instructions?|assistant|developer)\b[^>]*>",
    re.IGNORECASE,
)

# Diretivas clássicas de prompt injection / jailbreak / exfiltração (PT + EN)
_INJECTION_RULES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "ignore_previous_en",
        re.compile(
            r"(?:ignore|disregard|forget|override|bypass)\s+"
            r"(?:all\s+|any\s+|everything\s+)?(?:the\s+)?"
            r"(?:previous|prior|above|preceding|earlier|existing|system|safety|security)\s+"
            r"(?:instructions?|prompts?|rules?|directives?|guidelines?|constraints?)[^\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "ignore_previous_pt",
        re.compile(
            r"(?:ignore|desconsidere|esque[cç]a|anule|sobrescreva|burl[ae])\s+"
            r"(?:todas?\s+as\s+|todos?\s+os\s+|as\s+|os\s+)?"
            r"(?:instru[cç][oõ]es|regras|diretrizes|mensagens|restri[cç][oõ]es|limites)\s+"
            r"(?:anteriores|acima|pr[eé]vias|do\s+sistema|de\s+seguran[cç]a)[^\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "role_hijack_en",
        re.compile(
            r"(?:you\s+are\s+now\b|from\s+now\s+on\s+you\s+are\b|"
            r"act\s+as\s+(?:a\s+|an\s+)?(?:unrestricted|jailbroken|root|admin|system|dan\b)|"
            r"pretend\s+(?:you\s+are|to\s+be)\s+(?:an?\s+)?(?:unrestricted|system|admin))[^\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "role_hijack_pt",
        re.compile(
            r"(?:(?:a\s+partir\s+de\s+agora\s+)?voc[eê]\s+agora\s+[eé]\b|"
            r"aja\s+como\s+(?:se\s+fosse\s+)?(?:um\s+|o\s+)?(?:administrador|sistema|root|sem\s+restri[cç][oõ]es)|"
            r"finja\s+ser\s+(?:um\s+|o\s+)?(?:administrador|sistema|root))[^\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_directive",
        re.compile(
            r"(?:(?:new\s+|override\s+|reveal\s+(?:your\s+|the\s+)?|show\s+(?:your\s+|the\s+)?|"
            r"revele\s+(?:o\s+|seu\s+)?|mostre\s+(?:o\s+|seu\s+)?)?"
            r"(?:system\s*prompt|prompt\s+de\s+sistema|hidden\s+instructions?)"
            r"(?:\s*:[^\n]*|[^\n]*))",
            re.IGNORECASE,
        ),
    ),
    (
        "delimiter_spoofing",
        re.compile(
            r"(?:\[\s*(?:SYSTEM|INST|SYS|DEVELOPER)\s*\]|"
            r"<\|(?:im_start|im_end|system|endoftext|assistant)\|>\s*[^\n]*|"
            r"(?:^|\n)###\s*(?:SYSTEM|INSTRUCTIONS?)\b[^\n]*|"
            r"\bnew\s+(?:system\s+)?instructions?\s*:[^\n]*|"
            r"\bnovas\s+instru[cç][oõ]es(?:\s+do\s+sistema)?\s*:[^\n]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "exfiltration_smuggling",
        re.compile(
            r"(?:(?:envie|mande|exfiltre|transmita|send|post|upload|leak|exfiltrate)\s+"
            r"(?:o\s+|os\s+|a\s+|as\s+|the\s+|your\s+|all\s+)?"
            r"(?:\.env|senhas?|passwords?|tokens?|chaves?|api[_\s-]?keys?|segredos?|secrets?|credenciais|credentials)"
            r"[^\n]*|"
            r"\b(?:enviar_alerta_webhook|executar_comando|run_command|call\s+tool|execute\s+tool)\s*[:(][^\n]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "security_bypass_directive",
        re.compile(
            r"(?:bypass|desative|disable)\s+(?:the\s+|o\s+|a\s+)?"
            r"(?:e2ee|lock|trava|cofre|auth|autentica[cç][aã]o|safety|seguran[cç]a)[^\n]*",
            re.IGNORECASE,
        ),
    ),
)


def _registrar_flag(flags: list[str], nome: str) -> None:
    if nome not in flags:
        flags.append(nome)


def sanitizar_conteudo_externo(
    texto: str,
    *,
    source: str = "",
    trust_level: str = TRUST_EXTERNAL_SANITIZED,
    aplicar_tag: bool = True,
) -> tuple[str, list[str]]:
    """
    Detecta e remove payloads de Indirect Prompt Injection (comentários HTML/JS ocultos,
    tags perigosas, caracteres zero-width, diretivas de sobrescrita/exfiltração em PT/EN
    e tentativas de fuga de tag) e envelopa conteúdo externo com tag limpa de isolamento.

    Returns:
        (texto_sanitizado, lista_de_deteccoes)
    """
    if not texto or not texto.strip():
        return "", []

    flags: list[str] = []
    limpo = texto

    # 1. Remove caracteres invisíveis / bidi (evita bypass por ofuscação Unicode)
    if _ZERO_WIDTH_RE.search(limpo):
        _registrar_flag(flags, "unicode_zero_width_obfuscation")
        limpo = _ZERO_WIDTH_RE.sub("", limpo)

    # 2. Inspeciona comentários HTML antes de removê-los para registrar diretivas ocultas
    for match in _HTML_COMMENT_RE.finditer(limpo):
        _registrar_flag(flags, "hidden_html_comment")
        interno = match.group(1)
        for nome_regra, pat in _INJECTION_RULES:
            if pat.search(interno):
                _registrar_flag(flags, nome_regra)
    limpo = _HTML_COMMENT_RE.sub(" ", limpo)

    # 3. Remove tags <script>, <style>, <iframe> e blocos CSS ocultos (display:none etc.)
    for match in _SCRIPT_STYLE_RE.finditer(limpo):
        _registrar_flag(flags, f"dangerous_tag_{match.group(1).lower()}")
        for nome_regra, pat in _INJECTION_RULES:
            if pat.search(match.group(0)):
                _registrar_flag(flags, nome_regra)
    limpo = _SCRIPT_STYLE_RE.sub(" ", limpo)

    for match in _HIDDEN_HTML_ELEMENT_RE.finditer(limpo):
        _registrar_flag(flags, "hidden_css_element")
        for nome_regra, pat in _INJECTION_RULES:
            if pat.search(match.group(0)):
                _registrar_flag(flags, nome_regra)
    limpo = _HIDDEN_HTML_ELEMENT_RE.sub(" ", limpo)

    # 4. Inspeciona e remove comentários de bloco JS /* ... */
    for match in _JS_BLOCK_COMMENT_RE.finditer(limpo):
        interno = match.group(1)
        _registrar_flag(flags, "js_block_comment")
        for nome_regra, pat in _INJECTION_RULES:
            if pat.search(interno):
                _registrar_flag(flags, nome_regra)
    limpo = _JS_BLOCK_COMMENT_RE.sub(" ", limpo)

    # 5. Neutraliza tentativas de breakout de tags (<external_knowledge>, <system>, etc.)
    if _TAG_BREAKOUT_RE.search(limpo):
        _registrar_flag(flags, "tag_breakout_attempt")
        limpo = _TAG_BREAKOUT_RE.sub(" ", limpo)

    # 6. Remove diretivas clássicas de prompt injection / jailbreak / exfiltração
    for nome_regra, pat in _INJECTION_RULES:
        if pat.search(limpo):
            _registrar_flag(flags, nome_regra)
            limpo = pat.sub("", limpo)

    # 7. Limpeza final de linhas vazias excessivas e espaços redundantes
    linhas_limpas: list[str] = []
    for linha in limpo.splitlines():
        l_strip = re.sub(r"[ \t]{2,}", " ", linha).strip()
        if l_strip:
            linhas_limpas.append(l_strip)
    corpo_final = "\n".join(linhas_limpas).strip()

    if not aplicar_tag:
        return corpo_final, flags

    safe_trust = html.escape(str(trust_level or TRUST_EXTERNAL_SANITIZED), quote=True)
    safe_source = html.escape(str(source).strip(), quote=True) if source else ""
    attr_source = f' source="{safe_source}"' if safe_source else ""
    attr_sanitized = ' sanitized="true"' if flags else ""

    if not corpo_final:
        corpo_final = "[Conteúdo externo vazio após sanitização de segurança]"

    tagged = (
        f'<external_knowledge trust="{safe_trust}"{attr_source}{attr_sanitized}>\n'
        f"{corpo_final}\n"
        f"</external_knowledge>"
    )
    return tagged, flags


# ---------------------------------------------------------------------------
# Armazenamento SQLite thread-safe com modo WAL
# ---------------------------------------------------------------------------

class MemoryV3Store:
    """
    Persistência SQLite thread-safe (modo WAL) para:
    - `session_turns`: histórico conversacional ordenado por sessão.
    - `memory_meta`: metadados temporais, taxonômicos e de importância das memórias.
    """

    def __init__(self, db_path: str | Path = DEFAULT_SESSIONS_DB_PATH) -> None:
        self._raw_path = str(db_path)
        self._is_memory = self._raw_path == ":memory:"
        self.db_path: Path | None = None if self._is_memory else Path(db_path).resolve()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn

        if not self._is_memory and self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        else:
            conn = sqlite3.connect(":memory:", check_same_thread=False)

        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_session_turns_sid_id
                    ON session_turns (session_id, id DESC);

                CREATE TABLE IF NOT EXISTS memory_meta (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL DEFAULT 'episodic',
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'conversation',
                    trust_level TEXT NOT NULL DEFAULT 'verified_internal'
                );
                CREATE INDEX IF NOT EXISTS idx_memory_meta_updated
                    ON memory_meta (updated_at DESC, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_meta_type
                    ON memory_meta (memory_type);
                """
            )
            conn.commit()

    def journal_mode(self) -> str:
        """Retorna o modo de journal atual do SQLite (ex.: 'wal' ou 'memory')."""
        with self._lock:
            row = self._connect().execute("PRAGMA journal_mode;").fetchone()
            return str(row[0]).lower() if row else ""

    def close(self) -> None:
        """Fecha a conexão SQLite de forma segura."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    # ---- Session Turns ----

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        created_at: float | None = None,
        max_turns: int = DEFAULT_MAX_SESSION_TURNS,
    ) -> int:
        """Insere um turno na sessão e poda turnos excedentes além de `max_turns`."""
        sid = (session_id or "default").strip() or "default"
        r = (role or "user").strip()
        c = (content or "").strip()
        if not c:
            return -1
        ts = time.time() if created_at is None else float(created_at)

        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (sid, r, c, ts),
            )
            row_id = int(cur.lastrowid or 0)
            if max_turns > 0:
                conn.execute(
                    """
                    DELETE FROM session_turns
                    WHERE session_id = ?
                      AND id NOT IN (
                          SELECT id FROM session_turns
                          WHERE session_id = ?
                          ORDER BY id DESC
                          LIMIT ?
                      )
                    """,
                    (sid, sid, int(max_turns)),
                )
            conn.commit()
            return row_id

    def append_exchange(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        created_at: float | None = None,
        max_turns: int = DEFAULT_MAX_SESSION_TURNS,
    ) -> None:
        """Insere atomicamente um par (user, assistant) na sessão."""
        sid = (session_id or "default").strip() or "default"
        u = (user_content or "").strip()
        a = (assistant_content or "").strip()
        if not u and not a:
            return
        ts = time.time() if created_at is None else float(created_at)

        with self._lock:
            conn = self._connect()
            if u:
                conn.execute(
                    "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                    (sid, u, ts),
                )
            if a:
                conn.execute(
                    "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
                    (sid, a, ts + 1e-6),
                )
            if max_turns > 0:
                conn.execute(
                    """
                    DELETE FROM session_turns
                    WHERE session_id = ?
                      AND id NOT IN (
                          SELECT id FROM session_turns
                          WHERE session_id = ?
                          ORDER BY id DESC
                          LIMIT ?
                      )
                    """,
                    (sid, sid, int(max_turns)),
                )
            conn.commit()

    def get_session_turns(
        self,
        session_id: str = "default",
        limit: int = DEFAULT_MAX_SESSION_TURNS,
    ) -> list[dict[str, Any]]:
        """Retorna os últimos `limit` turnos da sessão em ordem cronológica crescente."""
        if limit <= 0:
            return []
        sid = (session_id or "default").strip() or "default"
        with self._lock:
            rows = self._connect().execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM (
                    SELECT id, session_id, role, content, created_at
                    FROM session_turns
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) sub
                ORDER BY id ASC
                """,
                (sid, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]

    def clear_session(self, session_id: str = "default") -> int:
        """Remove todos os turnos de uma sessão específica."""
        sid = (session_id or "default").strip() or "default"
        with self._lock:
            conn = self._connect()
            cur = conn.execute("DELETE FROM session_turns WHERE session_id = ?", (sid,))
            conn.commit()
            return int(cur.rowcount or 0)

    def list_sessions(self) -> list[str]:
        """Lista os IDs de sessão com histórico persistido."""
        with self._lock:
            rows = self._connect().execute(
                "SELECT DISTINCT session_id FROM session_turns ORDER BY session_id ASC"
            ).fetchall()
            return [str(r["session_id"]) for r in rows]

    # ---- Memory Metadata Index ----

    def upsert_memory_meta(
        self,
        memory_id: str,
        memory_type: str = MEMORY_TYPE_EPISODIC,
        importance: float = 0.5,
        created_at: float | None = None,
        updated_at: float | None = None,
        access_count: int | None = None,
        source: str = "conversation",
        trust_level: str = TRUST_VERIFIED_INTERNAL,
    ) -> dict[str, Any]:
        """Insere ou atualiza metadados estruturados de uma memória."""
        now = time.time()
        mtype = memory_type if memory_type in VALID_MEMORY_TYPES else MEMORY_TYPE_EPISODIC
        imp = max(0.0, min(1.0, float(importance)))

        with self._lock:
            conn = self._connect()
            existing = conn.execute(
                "SELECT * FROM memory_meta WHERE id = ?",
                (memory_id,),
            ).fetchone()

            if existing is not None:
                c_at = float(existing["created_at"]) if created_at is None else float(created_at)
                u_at = now if updated_at is None else float(updated_at)
                acc = (int(existing["access_count"]) + 1) if access_count is None else int(access_count)
                final_imp = max(float(existing["importance"]), imp)
                conn.execute(
                    """
                    UPDATE memory_meta
                    SET memory_type = ?, importance = ?, created_at = ?, updated_at = ?,
                        access_count = ?, source = ?, trust_level = ?
                    WHERE id = ?
                    """,
                    (mtype, final_imp, c_at, u_at, acc, source, trust_level, memory_id),
                )
            else:
                c_at = now if created_at is None else float(created_at)
                u_at = c_at if updated_at is None else float(updated_at)
                acc = 0 if access_count is None else int(access_count)
                final_imp = imp
                conn.execute(
                    """
                    INSERT INTO memory_meta
                        (id, memory_type, importance, created_at, updated_at, access_count, source, trust_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (memory_id, mtype, final_imp, c_at, u_at, acc, source, trust_level),
                )
            conn.commit()
            return {
                "id": memory_id,
                "memory_type": mtype,
                "importance": final_imp,
                "created_at": c_at,
                "updated_at": u_at,
                "access_count": acc,
                "source": source,
                "trust_level": trust_level,
            }

    def get_memory_meta(self, memory_id: str) -> dict[str, Any] | None:
        """Retorna metadados de uma memória pelo ID."""
        with self._lock:
            row = self._connect().execute(
                "SELECT * FROM memory_meta WHERE id = ?",
                (memory_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def get_many_memory_meta(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Busca metadados em lote para múltiplos IDs."""
        if not memory_ids:
            return {}
        placeholders = ",".join("?" for _ in memory_ids)
        with self._lock:
            rows = self._connect().execute(
                f"SELECT * FROM memory_meta WHERE id IN ({placeholders})",
                tuple(memory_ids),
            ).fetchall()
            return {str(r["id"]): dict(r) for r in rows}

    def touch_memory(self, memory_id: str) -> None:
        """Incrementa contador de acesso quando uma memória é recuperada."""
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE memory_meta SET access_count = access_count + 1 WHERE id = ?",
                (memory_id,),
            )
            conn.commit()

    def list_memory_meta(
        self,
        limit: int = 50,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista metadados ordenados cronologicamente do mais recente para o mais antigo."""
        if limit <= 0:
            return []
        with self._lock:
            conn = self._connect()
            if memory_type:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_meta
                    WHERE memory_type = ?
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT ?
                    """,
                    (memory_type, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_meta
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]

    def delete_memory_meta(self, memory_id: str) -> bool:
        """Remove metadados de uma memória pelo ID."""
        with self._lock:
            conn = self._connect()
            cur = conn.execute("DELETE FROM memory_meta WHERE id = ?", (memory_id,))
            conn.commit()
            return bool(cur.rowcount and cur.rowcount > 0)

    def count_memories(self, memory_type: str | None = None) -> int:
        """Conta registros indexados em memory_meta."""
        with self._lock:
            conn = self._connect()
            if memory_type:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memory_meta WHERE memory_type = ?",
                    (memory_type,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM memory_meta").fetchone()
            return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Singleton seguro do store padrão (isolado em memória sob pytest)
# ---------------------------------------------------------------------------

_DEFAULT_STORE_LOCK = threading.Lock()
_DEFAULT_STORE: MemoryV3Store | None = None


def _is_pytest_running() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


def get_default_store() -> MemoryV3Store:
    """
    Retorna o `MemoryV3Store` padrão.
    Em execução sob `PYTEST_CURRENT_TEST` (sem override explícito via `FRYIVS_SESSIONS_DB`),
    utiliza banco SQLite em memória (`:memory:`) para nunca poluir `data/sessions.db`.
    """
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is not None:
            return _DEFAULT_STORE

        env_path = (os.getenv("FRYIVS_SESSIONS_DB") or "").strip()
        if env_path:
            _DEFAULT_STORE = MemoryV3Store(env_path)
        elif _is_pytest_running():
            _DEFAULT_STORE = MemoryV3Store(":memory:")
        else:
            _DEFAULT_STORE = MemoryV3Store(DEFAULT_SESSIONS_DB_PATH)
        return _DEFAULT_STORE


def configure_default_store(db_path: str | Path | MemoryV3Store) -> MemoryV3Store:
    """Substitui o store padrão (útil para testes ou configuração customizada)."""
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is not None and _DEFAULT_STORE is not db_path:
            try:
                _DEFAULT_STORE.close()
            except Exception:
                pass
        if isinstance(db_path, MemoryV3Store):
            _DEFAULT_STORE = db_path
        else:
            _DEFAULT_STORE = MemoryV3Store(db_path)
        return _DEFAULT_STORE


def reset_default_store() -> None:
    """Fecha e limpa o singleton do store padrão."""
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is not None:
            try:
                _DEFAULT_STORE.close()
            finally:
                _DEFAULT_STORE = None
