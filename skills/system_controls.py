"""
Módulo de controle do sistema e automação de interface (GUI) para F.R.Y.I.Vs.
Implementa tipagem estrita (Python 3.12+), tratamento robusto de exceções e esquemas validados.
"""

from __future__ import annotations

import os
import time
from typing import Final, Literal
from pydantic import BaseModel, Field

try:
    import pyautogui
    import pygetwindow as gw
except ImportError:
    pyautogui = None
    gw = None

if pyautogui is not None:
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.1

VolumeAction = Literal["aumentar", "diminuir", "mutar"]


class JanelaParams(BaseModel):
    """Parâmetros para manipulação de janelas."""
    titulo: str = Field(..., description="Nome ou parte do título da janela")


class DigitarTextoParams(BaseModel):
    """Parâmetros para digitação de texto."""
    texto: str = Field(..., description="Texto a ser digitado na janela ativa")


class AtalhoParams(BaseModel):
    """Parâmetros para execução de atalhos de teclado."""
    teclas: list[str] | str = Field(
        ...,
        description="Lista de teclas combinadas (ex: ['ctrl', 'c']) ou string (ex: 'ctrl+c')"
    )


class ControlarVolumeParams(BaseModel):
    """Parâmetros para controle de volume do áudio."""
    acao: VolumeAction = Field(
        ...,
        description="Ação do volume: 'aumentar', 'diminuir' ou 'mutar'"
    )


class ScreenshotParams(BaseModel):
    """Parâmetros opcionais para captura de tela."""
    nome_arquivo: str | None = Field(
        default=None,
        description="Nome opcional para o arquivo da imagem (ex: 'captura.png')"
    )


def listar_janelas() -> str:
    """Lista os títulos das janelas ativas e visíveis no sistema operacional."""
    if gw is None:
        return "Erro: A biblioteca 'pygetwindow' não está instalada ou disponível no sistema."
    try:
        windows = gw.getAllTitles()
        titulos_validos = [t.strip() for t in windows if t and t.strip()]
        if not titulos_validos:
            return "Nenhuma janela ativa visível encontrada no momento."
        
        lista_formatada = "\n".join(f"- {t}" for t in titulos_validos[:15])
        return f"Janelas abertas ({len(titulos_validos)} encontradas):\n{lista_formatada}"
    except Exception as e:
        return f"Erro ao listar janelas abertas: {e}"


def focar_janela(titulo: str) -> str:
    """Procura uma janela por parte do título e a traz para o primeiro plano."""
    if gw is None:
        return "Erro: A biblioteca 'pygetwindow' não está instalada."
    if not titulo or not titulo.strip():
        return "Erro: O título da janela não pode estar vazio."
    try:
        query = titulo.strip()
        windows = gw.getWindowsWithTitle(query)
        if not windows:
            return f"Nenhuma janela contendo '{query}' foi encontrada."
        
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        return f"Janela '{win.title}' colocada em foco com sucesso."
    except Exception as e:
        return f"Erro ao focar janela '{titulo}': {e}"


def minimizar_janela(titulo: str) -> str:
    """Minimiza uma janela ativa pelo título."""
    if gw is None:
        return "Erro: A biblioteca 'pygetwindow' não está instalada."
    if not titulo or not titulo.strip():
        return "Erro: O título da janela não pode estar vazio."
    try:
        query = titulo.strip()
        windows = gw.getWindowsWithTitle(query)
        if not windows:
            return f"Janela contendo '{query}' não encontrada."
        
        win = windows[0]
        win.minimize()
        return f"Janela '{win.title}' minimizada com sucesso."
    except Exception as e:
        return f"Erro ao minimizar janela '{titulo}': {e}"


def maximizar_janela(titulo: str) -> str:
    """Maximiza uma janela pelo título."""
    if gw is None:
        return "Erro: A biblioteca 'pygetwindow' não está instalada."
    if not titulo or not titulo.strip():
        return "Erro: O título da janela não pode estar vazio."
    try:
        query = titulo.strip()
        windows = gw.getWindowsWithTitle(query)
        if not windows:
            return f"Janela contendo '{query}' não encontrada."
        
        win = windows[0]
        win.maximize()
        return f"Janela '{win.title}' maximizada com sucesso."
    except Exception as e:
        return f"Erro ao maximizar janela '{titulo}': {e}"


def fechar_janela(titulo: str) -> str:
    """Fecha uma janela aberta pelo título."""
    if gw is None:
        return "Erro: A biblioteca 'pygetwindow' não está instalada."
    if not titulo or not titulo.strip():
        return "Erro: O título da janela não pode estar vazio."
    try:
        query = titulo.strip()
        windows = gw.getWindowsWithTitle(query)
        if not windows:
            return f"Janela contendo '{query}' não encontrada."
        
        win = windows[0]
        win.close()
        return f"Janela '{win.title}' fechada com sucesso."
    except Exception as e:
        return f"Erro ao fechar janela '{titulo}': {e}"


def digitar_texto(texto: str) -> str:
    """Digita um texto automaticamente na janela com foco ativo."""
    if pyautogui is None:
        return "Erro: A biblioteca 'pyautogui' não está instalada."
    if not texto:
        return "Aviso: Nenhum texto fornecido para digitação."
    try:
        time.sleep(0.3)
        pyautogui.write(texto, interval=0.03)
        return f"Texto digitado com sucesso ({len(texto)} caracteres)."
    except Exception as e:
        return f"Erro ao digitar texto: {e}"


def _parse_keys(teclas: list[str] | str) -> list[str]:
    """Auxiliar para converter atalhos em strings compostas ou listas normalizadas."""
    if isinstance(teclas, str):
        delimiters = ["+", ","]
        for d in delimiters:
            if d in teclas:
                return [k.strip().lower() for k in teclas.split(d) if k.strip()]
        return [teclas.strip().lower()]
    return [str(k).strip().lower() for k in teclas if str(k).strip()]


def pressionar_atalho(teclas: list[str] | str) -> str:
    """Pressiona uma combinação de teclas de atalho (ex: ['ctrl', 'c'], ['alt', 'tab'], ['win', 'd'])."""
    if pyautogui is None:
        return "Erro: A biblioteca 'pyautogui' não está instalada."
    
    parsed_keys = _parse_keys(teclas)
    if not parsed_keys:
        return "Erro: Nenhuma tecla válida informada para o atalho."
    
    try:
        pyautogui.hotkey(*parsed_keys)
        return f"Atalho '{' + '.join(parsed_keys)}' executado com sucesso."
    except Exception as e:
        return f"Erro ao pressionar atalho {' + '.join(parsed_keys)}: {e}"


def controlar_volume(acao: str) -> str:
    """Controla o volume do sistema: 'aumentar', 'diminuir' ou 'mutar'."""
    acao_norm = acao.lower().strip()
    
    if pyautogui is None:
        return "Erro: A biblioteca 'pyautogui' não está instalada."
    try:
        if acao_norm in ["aumentar", "up", "mais", "alto"]:
            for _ in range(5):
                pyautogui.press("volumeup")
            return "Volume aumentado com sucesso."
        elif acao_norm in ["diminuir", "down", "menos", "baixo"]:
            for _ in range(5):
                pyautogui.press("volumedown")
            return "Volume diminuído com sucesso."
        elif acao_norm in ["mutar", "desmutar", "mute", "silenciar", "mudo"]:
            pyautogui.press("volumemute")
            return "Volume mutado/desmutado com sucesso."
        else:
            return f"Ação de volume desconhecida: '{acao}'. Use 'aumentar', 'diminuir' ou 'mutar'."
    except Exception as e_pag:
        if os.name == "nt":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                VK_VOLUME_MUTE = 0xAD
                VK_VOLUME_DOWN = 0xAE
                VK_VOLUME_UP = 0xAF
                if acao_norm in ["aumentar", "up", "mais", "alto"]:
                    for _ in range(5):
                        user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                        user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
                    return "Volume aumentado com sucesso."
                elif acao_norm in ["diminuir", "down", "menos", "baixo"]:
                    for _ in range(5):
                        user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                        user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
                    return "Volume diminuído com sucesso."
                elif acao_norm in ["mutar", "desmutar", "mute", "silenciar", "mudo"]:
                    user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                    user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                    return "Volume mutado/desmutado com sucesso."
            except Exception:
                pass
        return f"Erro ao ajustar volume: {e_pag}"


def _win32_native_screenshot(caminho: str) -> bool:
    """Captura de tela nativa do Windows via GDI/BitBlt (funciona sem falhas mesmo em ambientes restritos)."""
    try:
        import ctypes
        import ctypes.wintypes
        from PIL import Image

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbitmap)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.wintypes.DWORD),
                ("biWidth", ctypes.wintypes.LONG),
                ("biHeight", ctypes.wintypes.LONG),
                ("biPlanes", ctypes.wintypes.WORD),
                ("biBitCount", ctypes.wintypes.WORD),
                ("biCompression", ctypes.wintypes.DWORD),
                ("biSizeImage", ctypes.wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.wintypes.LONG),
                ("biYPelsPerMeter", ctypes.wintypes.LONG),
                ("biClrUsed", ctypes.wintypes.DWORD),
                ("biClrImportant", ctypes.wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        img.save(caminho)

        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        return True
    except Exception as e:
        print(f"[SystemControls] Win32 Screenshot falhou: {e}")
        return False


def tirar_screenshot(nome_arquivo: str | None = None) -> str:
    """Tira uma captura da tela inteira e salva em arquivo PNG."""
    try:
        pasta_destino = "screenshots"
        os.makedirs(pasta_destino, exist_ok=True)
        
        if not nome_arquivo or not nome_arquivo.strip():
            timestamp = int(time.time())
            nome_arquivo = f"screenshot_{timestamp}.png"
        else:
            nome_arquivo = os.path.basename(nome_arquivo.strip())
            if not nome_arquivo.lower().endswith(".png"):
                nome_arquivo += ".png"

        caminho = os.path.join(pasta_destino, nome_arquivo)

        if pyautogui is None:
            return "Erro: A biblioteca 'pyautogui' não está instalada."

        try:
            screenshot = pyautogui.screenshot()
            screenshot.save(caminho)
            return f"Captura de tela salva com sucesso em '{caminho}'."
        except Exception as e_pag:
            if os.name == "nt":
                if _win32_native_screenshot(caminho):
                    return f"Captura de tela salva com sucesso em '{caminho}'."
            return f"Erro ao capturar tela: {e_pag}"
    except Exception as e:
        return f"Erro ao capturar tela: {e}"


def obter_hora_data() -> str:
    """Retorna o dia da semana, data e hora atual do sistema operacional."""
    import datetime
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    agora = datetime.datetime.now()
    dia_semana = dias[agora.weekday()]
    mes_nome = meses[agora.month - 1]
    return f"Agora são {agora.strftime('%H:%M')}. Hoje é {dia_semana}, {agora.day} de {mes_nome} de {agora.year}."


def _abrir_url_navegador_visivel(url: str) -> None:
    """Abre URL em Chrome ou Edge garantindo janela visível e foco na tela do usuário."""
    import os
    import sys
    import subprocess
    import time
    
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    candidatos = [edge_path, chrome_path]
    aberto = False
    for exe in candidatos:
        if os.path.exists(exe):
            cmd = [exe, "--new-window", "--start-maximized", url]
            if sys.platform == "win32":
                try:
                    STARTF_USESHOWWINDOW = 0x1
                    SW_SHOW = 5
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= STARTF_USESHOWWINDOW
                    si.wShowWindow = SW_SHOW
                    subprocess.Popen(cmd, startupinfo=si)
                    aberto = True
                    break
                except Exception:
                    pass
            try:
                subprocess.Popen(cmd)
                aberto = True
                break
            except Exception:
                pass
            
    if not aberto:
        import webbrowser
        webbrowser.open_new(url)
        
    try:
        import ctypes
        import win32gui
        import win32con

        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)

        time.sleep(0.4)
        def _enum_w(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd)
                if any(b in text.lower() for b in ["chrome", "edge"]):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                    win32gui.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)

        win32gui.EnumWindows(_enum_w, None)
    except Exception:
        pass

    try:
        if gw is not None:
            time.sleep(0.3)
            for t in ["Google Chrome", "Microsoft Edge", "Chrome", "Edge"]:
                wins = gw.getWindowsWithTitle(t)
                if wins:
                    for w in wins:
                        if w.isMinimized:
                            w.restore()
                        w.maximize()
                        w.activate()
                    break
    except Exception:
        pass


def _abrir_navegador_segundo_plano(url: str, navegador: str = "chrome") -> str:
    """Abre URL diretamente no Chrome ou Edge mantendo a janela em segundo plano (sem roubar foco)."""
    import os
    import sys
    import subprocess

    nav_lower = (navegador or "chrome").lower().strip()
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    if "edge" in nav_lower and os.path.exists(edge_path):
        target_exe = edge_path
        nome_nav = "Microsoft Edge"
    elif os.path.exists(chrome_path):
        target_exe = chrome_path
        nome_nav = "Google Chrome"
    elif os.path.exists(edge_path):
        target_exe = edge_path
        nome_nav = "Microsoft Edge"
    else:
        target_exe = None
        nome_nav = "navegador padrão"

    if target_exe:
        cmd = [target_exe, "--new-window", url]
        if sys.platform == "win32":
            try:
                STARTF_USESHOWWINDOW = 0x1
                SW_SHOWNOACTIVATE = 4
                si = subprocess.STARTUPINFO()
                si.dwFlags |= STARTF_USESHOWWINDOW
                si.wShowWindow = SW_SHOWNOACTIVATE
                subprocess.Popen(cmd, startupinfo=si)
                return f"{nome_nav} em segundo plano"
            except Exception:
                pass
        subprocess.Popen(cmd)
        return f"{nome_nav} em segundo plano"
    else:
        import webbrowser
        webbrowser.open_new(url)
        return f"{nome_nav} aberto"


def pesquisar_google(termo: str, navegador: str = "chrome") -> str:
    """
    Pesquisa um termo no Google abrindo/reutilizando a aba do navegador Co-Piloto (Selenium)
    para permitir abrir links, clicar em resultados e navegar na mesma aba.
    """
    if not termo or not str(termo).strip():
        return "Erro: O termo de pesquisa não pode estar vazio."
    t = str(termo).strip()
    import urllib.parse
    url = f"https://www.google.com/search?q={urllib.parse.quote(t)}"
    try:
        from core.session_state import registrar_artefato
        registrar_artefato("web", url=url, titulo=t)
    except Exception:
        pass
    from core.overlay import _em_teste, status_overlay
    if not _em_teste():
        status_overlay(f"● MODO CO-PILOTO WEB: Pesquisando '{t}'...", ativo=True, duracao=180.0)
        try:
            from skills.web_automation import pesquisar_na_web
            return pesquisar_na_web(t, motor="google", navegador=navegador)
        except Exception:
            pass
    detalhes = _abrir_navegador_segundo_plano(url, navegador=navegador)
    return f"Pesquisa sobre '{t}' iniciada no {detalhes}."


def pesquisar_informacao_web(termo: str) -> str:
    """
    Pesquisa informações, fatos, dúvidas ou notícias na internet em segundo plano (sem abrir navegador)
    e retorna os dados para responder diretamente no chat para o usuário.
    """
    t = (termo or "").strip()
    if not t:
        return "Nenhum termo de pesquisa fornecido, senhor."

    resultados = []
    links_encontrados: list[dict[str, str]] = []
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS(timeout=4) as ddgs:
                res = list(ddgs.text(t, max_results=3))
                for idx, item in enumerate(res, start=1):
                    title = item.get("title", "").strip()
                    snippet = item.get("body", "").strip()
                    href = (item.get("href") or item.get("url") or "").strip()
                    if snippet:
                        url_str = f" ({href})" if href else ""
                        resultados.append(f"• {title}{url_str}: {snippet}")
                    if href:
                        links_encontrados.append({
                            "indice": str(idx),
                            "texto": title or href,
                            "url": href,
                        })
    except Exception:
        pass

    if links_encontrados:
        try:
            from skills.web_automation import _manager
            _manager.ultimos_links = links_encontrados
        except Exception:
            pass

    if not resultados or len(resultados) < 2:
        try:
            import urllib.request, urllib.parse, json
            wiki_url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(t)}"
            req = urllib.request.Request(wiki_url, headers={"User-Agent": "FRYIVS-AI/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                extract = data.get("extract", "")
                if extract:
                    resultados.append(f"• Wikipédia: {extract}")
        except Exception:
            pass

    if resultados:
        return "Informações encontradas na internet:\n" + "\n".join(resultados)
    return f"Não foram encontrados dados detalhados na internet para '{t}'."


def pesquisar_youtube(termo: str) -> str:
    """Pesquisa ou toca um vídeo/música no YouTube abrindo o navegador Co-Piloto com controle total da aba."""
    if not termo or not str(termo).strip():
        return "Erro: O termo de pesquisa não pode estar vazio."
    t = str(termo).strip()
    from core.overlay import _em_teste, status_overlay
    if not _em_teste():
        status_overlay(f"● MODO CO-PILOTO YOUTUBE: '{t}'...", ativo=True, duracao=180.0)
        try:
            from skills.web_automation import pesquisar_na_web
            return pesquisar_na_web(t, motor="youtube", navegador="chrome")
        except Exception:
            pass
    import urllib.parse
    query = urllib.parse.quote(t)
    url = f"https://www.youtube.com/results?search_query={query}"
    _abrir_url_navegador_visivel(url)
    return f"YouTube aberto na tela pesquisando por '{t}'."


def status_sistema() -> str:
    """Retorna o status atual de CPU, memória RAM e bateria do computador."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_used_gb = round(ram.used / (1024 ** 3), 1)
        ram_total_gb = round(ram.total / (1024 ** 3), 1)
        info = f"CPU em {cpu}%, Memória RAM em {ram_percent}% ({ram_used_gb} GB de {ram_total_gb} GB em uso)."
        battery = psutil.sensors_battery()
        if battery:
            plugged = "conectado à tomada" if battery.power_plugged else "na bateria"
            info += f" Bateria em {battery.percent}% ({plugged})."
        return info
    except Exception as e:
        return f"Status do sistema verificado: sistema operacional ativo. Detalhes: {e}"


def bloquear_tela() -> str:
    """Bloqueia a tela do computador (Windows LockWorkStation)."""
    import subprocess
    try:
        subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True, check=True)
        return "Tela do computador bloqueada com sucesso."
    except Exception as e:
        return f"Erro ao bloquear a tela: {e}"


SYSTEM_TOOLS_SCHEMAS: Final[list[dict[str, object]]] = [
    {
        "type": "function",
        "function": {
            "name": "listar_janelas",
            "description": "Lista todas as janelas e programas abertos visíveis no Windows",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "focar_janela",
            "description": "Foca e traz para primeiro plano uma janela aberta pelo nome ou parte do título",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Nome ou parte do título da janela a ser focada"}
                },
                "required": ["titulo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "minimizar_janela",
            "description": "Minimiza uma janela pelo título",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título ou parte do nome da janela"}
                },
                "required": ["titulo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "maximizar_janela",
            "description": "Maximiza uma janela pelo título",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título ou parte do nome da janela"}
                },
                "required": ["titulo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fechar_janela",
            "description": "Fecha uma janela aberta pelo título",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título ou parte do nome da janela a fechar"}
                },
                "required": ["titulo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "digitar_texto",
            "description": "Digita um texto automaticamente no aplicativo que estiver com o cursor ativo",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a ser digitado"}
                },
                "required": ["texto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pressionar_atalho",
            "description": "Executa uma combinação de teclas de atalho no sistema (ex: ['ctrl', 'c'], ['alt', 'tab'], ['win', 'd'] ou 'ctrl+c')",
            "parameters": {
                "type": "object",
                "properties": {
                    "teclas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de teclas para pressionar em conjunto, ex: ['ctrl', 'v'] ou 'ctrl+v'"
                    }
                },
                "required": ["teclas"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "controlar_volume",
            "description": "Ajusta ou muta o som do computador ('aumentar', 'diminuir' ou 'mutar')",
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "enum": ["aumentar", "diminuir", "mutar"],
                        "description": "Ação a executar no volume: 'aumentar', 'diminuir' ou 'mutar'"
                    }
                },
                "required": ["acao"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tirar_screenshot",
            "description": "Tira um print/captura de tela e salva como imagem PNG",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_arquivo": {
                        "type": "string",
                        "description": "Nome opcional do arquivo da imagem (ex: 'tela_jogo.png')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "obter_hora_data",
            "description": "Informa a hora exata, dia da semana e data atual",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_informacao_web",
            "description": (
                "Pesquisa informações, fatos, dúvidas ou notícias na internet em segundo plano SEM abrir nenhuma janela de navegador. "
                "Use SEMPRE que o usuário pedir para pesquisar algo, tirar dúvidas ou buscar na web, "
                "sem ter pedido explicitamente para abrir a janela do Chrome ou do Edge. "
                "O resultado da pesquisa deve ser sintetizado e respondido diretamente no chat com cortesia, tratando o usuário como 'senhor'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Assunto, pergunta ou termo a ser pesquisado na internet"}
                },
                "required": ["termo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_google",
            "description": (
                "Abre a janela do navegador (Google Chrome ou Edge) em segundo plano com a pesquisa realizada. "
                "ATENÇÃO: Use esta ferramenta APENAS quando o usuário pedir expressamente para ABRIR o navegador "
                "(ex: 'abra o chrome e pesquise', 'pesquise no chrome', 'abra o edge e pesquise', 'pesquise no navegador'). "
                "Se o usuário apenas pedir para pesquisar ou tirar dúvidas SEM citar Chrome ou Edge, use 'pesquisar_informacao_web'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Termo de busca a ser pesquisado no Google"},
                    "navegador": {
                        "type": "string",
                        "description": "Navegador a ser aberto: 'chrome' (padrão) ou 'edge'"
                    }
                },
                "required": ["termo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_youtube",
            "description": "Pesquisa vídeos, canais ou toca músicas no YouTube abrindo o navegador",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Música, artista ou vídeo a pesquisar no YouTube"}
                },
                "required": ["termo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "status_sistema",
            "description": "Mostra o consumo de processamento CPU, memória RAM e status da bateria",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bloquear_tela",
            "description": "Bloqueia a tela do computador imediatamente para segurança",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]
