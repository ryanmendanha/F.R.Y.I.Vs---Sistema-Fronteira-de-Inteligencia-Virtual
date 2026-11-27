"""
Gerenciamento central de Modo de Execução (Desktop vs. Web Cloud) e Diretórios Persistentes
da F.R.Y.I.Vs.

- Modo `desktop` (padrão local no Windows): mantém 100% das automações locais de SO,
  microfone físico em segundo plano (`VoiceDaemon`), overlay e pastas na raiz do projeto.
- Modo `web` (container Docker / Railway / Cloud): desativa skills exclusivas da área de
  trabalho física, centraliza persistência em `FRYIVS_DATA_DIR` / `RAILWAY_VOLUME_MOUNT_PATH`
  e habilita voz via WebAudio + workspace de download/upload de arquivos.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final, Literal

RuntimeMode = Literal["desktop", "web"]

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

DESKTOP_ONLY_SKILLS: Final[frozenset[str]] = frozenset(
    {
        "abrir_programa",
        "listar_janelas",
        "focar_janela",
        "minimizar_janela",
        "maximizar_janela",
        "fechar_janela",
        "digitar_texto",
        "pressionar_atalho",
        "controlar_volume",
        "tirar_screenshot",
        "bloquear_tela",
        "localizar_e_clicar_imagem",
        "ler_texto_da_tela",
        "navegar_para",
        "pesquisar_na_web",
        "clicar_elemento_web",
        "interagir_pagina_web",
        "digitar_campo_web",
        "ler_conteudo_pagina",
        "capturar_tela_web",
        "fechar_navegador",
        "abrir_planilha",
        "abrir_documento_word",
        "pesquisar_google",
        "pesquisar_youtube",
    }
)


def get_runtime_mode() -> RuntimeMode:
    """Retorna `'web'` ou `'desktop'` com base em `FRYIVS_MODE` ou variáveis de plataforma Cloud."""
    explicit = os.getenv("FRYIVS_MODE", "").strip().lower()
    if explicit in ("web", "cloud", "railway", "production"):
        return "web"
    if explicit in ("desktop", "local"):
        return "desktop"
    if any(
        os.getenv(k, "").strip()
        for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RENDER", "FLY_APP_NAME")
    ):
        return "web"
    return "desktop"


def is_web_mode() -> bool:
    return get_runtime_mode() == "web"


def get_data_dir() -> Path:
    """
    Diretório base para dados persistentes mutáveis (ChromaDB, SQLite, cache de áudio e arquivos).
    Prioriza `FRYIVS_DATA_DIR`, depois `RAILWAY_VOLUME_MOUNT_PATH`, ou raiz do projeto em modo desktop.
    """
    explicit = os.getenv("FRYIVS_DATA_DIR", "").strip() or os.getenv(
        "RAILWAY_VOLUME_MOUNT_PATH", ""
    ).strip()
    if explicit:
        p = Path(explicit).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    return PROJECT_ROOT


def get_chroma_dir() -> Path:
    d = get_data_dir() / "fryvis_memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_sessions_db_path() -> Path:
    d = get_data_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "sessions.db"


def get_audio_cache_dir() -> Path:
    d = get_data_dir() / "audio_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_files_workspace_dir() -> Path:
    base = get_data_dir()
    if is_web_mode() or base != PROJECT_ROOT:
        d = base / "arquivos_fryivs"
    else:
        d = PROJECT_ROOT / "planilhas-fryivs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_skill_allowed_in_mode(skill_name: str) -> bool:
    if not is_web_mode():
        return True
    return skill_name not in DESKTOP_ONLY_SKILLS


def filter_active_skill_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not is_web_mode():
        return schemas
    return [
        s
        for s in schemas
        if is_skill_allowed_in_mode(str(s.get("function", {}).get("name", "")))
    ]
