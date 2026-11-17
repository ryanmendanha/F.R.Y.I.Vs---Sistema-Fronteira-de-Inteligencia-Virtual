"""
Skill para abrir programas e aplicativos no sistema operacional.
Compatível com nomes em português, apelidos populares e comandos executáveis nativos do Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unicodedata
from typing import Final
from pydantic import BaseModel, Field

WINDOWS_APP_ALIASES: Final[dict[str, str]] = {
    "bloco de notas": "notepad.exe",
    "bloco de nota": "notepad.exe",
    "notepad": "notepad.exe",
    "notas": "notepad.exe",
    "wordpad": "wordpad.exe",

    "calculadora": "calc.exe",
    "calc": "calc.exe",
    "explorador de arquivos": "explorer.exe",
    "explorador": "explorer.exe",
    "explorer": "explorer.exe",
    "meu computador": "explorer.exe",
    "arquivos": "explorer.exe",
    "pastas": "explorer.exe",
    "gerenciador de tarefas": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "configuracoes": "ms-settings:",
    "configuracao": "ms-settings:",
    "settings": "ms-settings:",
    "painel de controle": "control.exe",
    "painel de controles": "control.exe",

    "prompt de comando": "cmd.exe",
    "prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "powershell": "powershell.exe",

    "navegador": "chrome.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "brave": "brave.exe",
    "opera": "opera.exe",

    "vscode": "code",
    "visual studio code": "code",
    "code": "code",
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",

    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "whatsapp": "whatsapp.exe",
    "telegram": "telegram.exe",
    "steam": "steam.exe",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "chatgpt": "https://chatgpt.com",
    "git bash": "git-bash.exe",
    "camera": "microsoft.windows.camera:",
    "fotos": "ms-photos:",
    "email": "outlookmail:",
    "gmail": "https://mail.google.com",
    "relogio": "ms-clock:",
    "alarme": "ms-clock:",
    "netflix": "https://www.netflix.com",
    "spotfy": "spotify.exe",
    "musica": "https://music.youtube.com",
    "noticias": "https://news.google.com",
    "previsao do tempo": "https://www.google.com/search?q=previsao+do+tempo",
    "clima": "https://www.google.com/search?q=previsao+do+tempo",
    "visual studio": "devenv.exe",
}

_KNOWN_WINDOWS_PATHS: Final[dict[str, list[str]]] = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "excel": [
        r"C:\Program Files\Microsoft Office\Office16\EXCEL.EXE",
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    ],
    "word": [
        r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
    ],
    "powerpoint": [
        r"C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE",
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    ]
}


class AbrirProgramaParams(BaseModel):
    """Parâmetros para a skill de abertura de programas."""
    nome_programa: str = Field(
        ...,
        description="Nome, apelido popular ou caminho do executável do programa (ex: 'Bloco de Notas', 'notepad', 'calculadora', 'chrome', 'edge', 'excel')"
    )
    argumentos: str | None = Field(
        default=None,
        description="Argumentos opcionais para o programa (ex: URL para navegador ou caminho de arquivo)"
    )


def _abrir_processo_visivel(cmd: list[str]) -> None:
    """Abre processo garantindo janela visível e sem supressão no Windows."""
    if sys.platform == "win32":
        try:
            STARTF_USESHOWWINDOW = 0x1
            SW_SHOW = 5
            si = subprocess.STARTUPINFO()
            si.dwFlags |= STARTF_USESHOWWINDOW
            si.wShowWindow = SW_SHOW
            subprocess.Popen(cmd, startupinfo=si)
            return
        except Exception:
            pass
    subprocess.Popen(cmd)


def _ativar_janela_navegador(titulos: list[str]) -> None:
    """Traz a janela do navegador para o primeiro plano na tela para o usuário ver."""
    try:
        import time
        import pygetwindow as gw
        time.sleep(0.6)
        for t in titulos:
            wins = gw.getWindowsWithTitle(t)
            if wins:
                for w in wins:
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                return
    except Exception:
        pass


def normalize_app_name(name: str) -> str:
    """
    Normaliza o nome do programa removendo acentos, espaços extras,
    extensões e caracteres separadores como sublinhados e hífens.
    """
    clean = name.strip().lower()
    
    if clean.endswith(".exe"):
        clean = clean[:-4].strip()

    clean = "".join(
        c for c in unicodedata.normalize("NFKD", clean)
        if not unicodedata.combining(c)
    )

    clean = clean.replace("_", " ").replace("-", " ")
    return " ".join(clean.split())


def resolve_program_name(nome_programa: str) -> str:
    """
    Resolve o nome fornecido pelo usuário/LLM para o comando executável correspondente.
    Verifica caminhos absolutos pré-existentes no Windows para evitar falhas silenciosas.
    """
    raw_clean = nome_programa.strip().lower()

    for chave, caminhos in _KNOWN_WINDOWS_PATHS.items():
        if chave in raw_clean or normalize_app_name(nome_programa) == chave:
            for c in caminhos:
                if os.path.exists(c):
                    return c
    
    if raw_clean in WINDOWS_APP_ALIASES:
        alvo = WINDOWS_APP_ALIASES[raw_clean]
        for chave, caminhos in _KNOWN_WINDOWS_PATHS.items():
            if chave in alvo.lower():
                for c in caminhos:
                    if os.path.exists(c):
                        return c
        return alvo

    norm_name = normalize_app_name(nome_programa)
    if norm_name in WINDOWS_APP_ALIASES:
        alvo = WINDOWS_APP_ALIASES[norm_name]
        for chave, caminhos in _KNOWN_WINDOWS_PATHS.items():
            if chave in alvo.lower():
                for c in caminhos:
                    if os.path.exists(c):
                        return c
        return alvo

    if os.path.exists(nome_programa):
        return nome_programa

    return nome_programa.strip()


def abrir_programa(nome_programa: str, argumentos: str | None = None) -> str:
    """
    Abre um programa no computador de forma inteligente e resiliente.
    Resolve apelidos populares, suporte a caminhos absolutos garantidos e pesquisas web embutidas.
    """
    if not nome_programa or not nome_programa.strip():
        return "Erro: O nome do programa não pode estar vazio."

    raw_lower = nome_programa.lower().strip()
    arg_lower = (argumentos or "").lower().strip()

    if any(b in arg_lower for b in ("edge", "chrome", "msedge", "navegador", "browser")) and not any(b in raw_lower for b in ("edge", "chrome", "msedge", "navegador", "browser")):
        navegador_escolhido = arg_lower
        site_ou_termo = nome_programa.strip()
        url = site_ou_termo if site_ou_termo.startswith(("http://", "https://")) else (f"https://www.{site_ou_termo}.com.br" if "." not in site_ou_termo else f"https://{site_ou_termo}")
        return abrir_programa(navegador_escolhido, url)

    if ("." in raw_lower or raw_lower in ("g1", "youtube", "globo", "google", "uol", "noticias")) and not raw_lower.endswith(".exe"):
        url = raw_lower if raw_lower.startswith(("http://", "https://")) else (f"https://{raw_lower}.globo.com" if raw_lower == "g1" else f"https://www.{raw_lower}.com.br")
        nav_padrao = "edge" if "edge" in arg_lower else "chrome"
        return abrir_programa(nav_padrao, url)

    if any(k in raw_lower for k in ("pesquise", "pesquisar", "procure", "busque")):
        import urllib.parse
        termo = raw_lower
        for prefixo in ("abra o edge e pesquise", "abra o chrome e pesquise", "abra o navegador e pesquise",
                        "abra o edge e", "abra o chrome e", "pesquise no edge", "pesquise no chrome",
                        "pesquise", "pesquisar", "procure", "busque"):
            if prefixo in termo:
                termo = termo.split(prefixo, 1)[-1]
                break
        termo = termo.strip().lstrip(":").strip()
        if termo:
            from core.overlay import _em_teste
            nav_pref = "edge" if "edge" in raw_lower else "chrome"
            if not _em_teste():
                try:
                    from skills.web_automation import pesquisar_na_web
                    return pesquisar_na_web(termo, motor="google", navegador=nav_pref)
                except Exception:
                    pass
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(termo)}"
            
            if "edge" in raw_lower:
                for c in _KNOWN_WINDOWS_PATHS["edge"]:
                    if os.path.exists(c):
                        _abrir_processo_visivel([c, "--new-window", "--start-maximized", url])
                        _ativar_janela_navegador(["Microsoft Edge", "Edge"])
                        return f"O Microsoft Edge foi aberto na tela com a pesquisa por '{termo}'."
            elif "chrome" in raw_lower:
                for c in _KNOWN_WINDOWS_PATHS["chrome"]:
                    if os.path.exists(c):
                        _abrir_processo_visivel([c, "--new-window", "--start-maximized", url])
                        _ativar_janela_navegador(["Google Chrome", "Chrome"])
                        return f"O Google Chrome foi aberto na tela com a pesquisa por '{termo}'."

            for c in _KNOWN_WINDOWS_PATHS["edge"] + _KNOWN_WINDOWS_PATHS["chrome"]:
                if os.path.exists(c):
                    _abrir_processo_visivel([c, "--new-window", "--start-maximized", url])
                    _ativar_janela_navegador(["Microsoft Edge", "Google Chrome", "Edge", "Chrome"])
                    return f"Navegador aberto na tela com a pesquisa por '{termo}'."

            os.startfile(url)
            _ativar_janela_navegador(["Microsoft Edge", "Google Chrome", "Edge", "Chrome"])
            return f"Navegador aberto com a pesquisa por '{termo}'."

    alvo = resolve_program_name(nome_programa)

    if sys.platform == "win32":
        is_browser = any(b in raw_lower or b in alvo.lower() for b in ("chrome", "msedge", "edge", "navegador"))
        if is_browser:
            from core.overlay import _em_teste
            url_alvo = argumentos if (argumentos and str(argumentos).strip()) else "https://www.google.com"
            nav_pref = "edge" if ("edge" in raw_lower or "edge" in alvo.lower()) else "chrome"
            if not _em_teste():
                try:
                    from skills.web_automation import navegar_para
                    return navegar_para(url_alvo, navegador=nav_pref)
                except Exception:
                    pass
            browser_args = ["--new-window", "--start-maximized", url_alvo]
            if os.path.isabs(alvo) and os.path.exists(alvo):
                _abrir_processo_visivel([alvo] + browser_args)
                _ativar_janela_navegador(["Google Chrome", "Microsoft Edge", "Chrome", "Edge"])
                return f"O navegador '{nome_programa}' foi aberto visivelmente na tela para navegar com você."

        if os.path.isabs(alvo) and os.path.exists(alvo):
            try:
                cmd = [alvo]
                if argumentos:
                    cmd.append(argumentos)
                _abrir_processo_visivel(cmd)
                return f"O aplicativo '{nome_programa}' foi aberto com sucesso."
            except Exception as e_abs:
                print(f"[abrir_programa] Erro no caminho absoluto ({e_abs}). Tentando os.startfile...")

        try:
            if argumentos:
                subprocess.Popen([alvo, argumentos])
            else:
                os.startfile(alvo)
            return f"O aplicativo '{nome_programa}' foi aberto com sucesso."
        except Exception as e_startfile:
            if alvo == "wt.exe":
                try:
                    os.startfile("powershell.exe")
                    return f"Windows Terminal não encontrado; PowerShell aberto com sucesso."
                except Exception:
                    pass

            cmd_path = shutil.which(alvo)
            if cmd_path:
                try:
                    cmd = [cmd_path]
                    if argumentos:
                        cmd.append(argumentos)
                    subprocess.Popen(cmd, shell=False)
                    return f"O aplicativo '{nome_programa}' foi aberto com sucesso."
                except Exception as e_popen:
                    return f"Erro ao iniciar '{cmd_path}': {e_popen}"

            try:
                cmd_str = f'"{alvo}" {argumentos}' if argumentos else f'"{alvo}"'
                subprocess.Popen(cmd_str, shell=True)
                return f"Comando '{alvo}' enviado ao sistema para execução."
            except Exception as e_shell:
                return (
                    f"Erro ao abrir '{nome_programa}' (resolvido como '{alvo}'): "
                    f"[WinError] O sistema não encontrou o aplicativo. Erros: {e_startfile} / {e_shell}"
                )

    try:
        cmd_open = ["open" if sys.platform == "darwin" else "xdg-open", alvo]
        if argumentos:
            cmd_open.append(argumentos)
        subprocess.Popen(cmd_open)
        return f"O aplicativo '{nome_programa}' foi aberto com sucesso."
    except Exception as e:
        return f"Erro ao abrir {nome_programa}: {e}"


SKILL_SCHEMA: Final[dict[str, object]] = {
    "type": "function",
    "function": {
        "name": "abrir_programa",
        "description": (
            "Abre um programa, aplicativo ou utilitário no computador pelo nome ou apelido "
            "(ex: 'Bloco de Notas', 'calculadora', 'Google Chrome', 'Edge', 'Excel', 'explorer', 'terminal')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome_programa": {
                    "type": "string",
                    "description": "Nome ou caminho do programa a abrir (ex: 'Bloco de Notas', 'notepad', 'calculadora', 'calc', 'chrome', 'edge', 'excel')"
                },
                "argumentos": {
                    "type": "string",
                    "description": "Argumentos opcionais para o programa (ex: URL ou caminho de arquivo)"
                }
            },
            "required": ["nome_programa"]
        }
    }
}