"""
Módulo de Automação Web Avançada com Selenium para F.R.Y.I.Vs.
Permite navegação completa, pesquisas no Google/YouTube, cliques em elementos,
preenchimento de formulários e extração de texto por comandos de voz ou texto.
"""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Any, Final, Literal
from pydantic import BaseModel, Field

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None
    ChromeOptions = None
    ChromeService = None
    EdgeOptions = None
    EdgeService = None
    By = None
    Keys = None
    WebDriverWait = None
    EC = None

try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    _WDM_AVAILABLE = True
except ImportError:
    _WDM_AVAILABLE = False
    ChromeDriverManager = None
    EdgeChromiumDriverManager = None


class NavegarWebParams(BaseModel):
    url: str = Field(..., description="URL ou endereço web a ser acessado (ex: 'https://google.com' ou 'github.com')")


class PesquisarWebParams(BaseModel):
    termo: str = Field(..., description="Termo, assunto ou pergunta a ser pesquisada na web")
    motor: Literal["google", "youtube", "duckduckgo", "bing"] = Field(
        default="google",
        description="Mecanismo de busca a utilizar ('google', 'youtube', 'duckduckgo' ou 'bing')"
    )


class ClicarWebParams(BaseModel):
    seletor: str | None = Field(
        default=None,
        description="Seletor CSS ou XPath do elemento a clicar (opcional se 'texto' for fornecido)"
    )
    texto: str | None = Field(
        default=None,
        description="Texto visível do botão ou link a clicar (ex: 'Entrar', 'Pesquisar', 'Vídeos')"
    )


class DigitarCampoWebParams(BaseModel):
    texto: str = Field(..., description="Texto ou dado a ser digitado no campo")
    seletor: str | None = Field(
        default=None,
        description="Seletor CSS ou XPath do campo de entrada (se omitido, digita no elemento em foco)"
    )
    submeter: bool = Field(
        default=True,
        description="Se deve pressionar Enter após a digitação"
    )


class LerConteudoWebParams(BaseModel):
    seletor: str | None = Field(
        default=None,
        description="Seletor CSS opcional de uma seção específica para ler. Se omitido, lê o corpo da página."
    )
    max_caracteres: int = Field(
        default=1200,
        description="Limite máximo de caracteres a retornar para síntese de voz"
    )


class CapturarTelaWebParams(BaseModel):
    nome_arquivo: str | None = Field(
        default=None,
        description="Nome opcional para o arquivo da captura de tela (ex: 'pagina_web.png')"
    )


class WebAutomationManager:
    """
    Gerenciador singleton de navegador para manter a sessão aberta
    entre comandos consecutivos do usuário (ex: pesquisar -> abrir link -> rolar -> clicar).
    """
    _instance: WebAutomationManager | None = None
    _driver: Any = None
    _active_browser: str = "chrome"
    ultimos_links: list[dict[str, str]] = []

    def __new__(cls) -> WebAutomationManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.ultimos_links = []
        return cls._instance

    def _aplicar_stealth(self, driver: Any) -> None:
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    )
                },
            )
        except Exception:
            pass

    def get_driver(self, browser_name: str | None = None) -> Any:
        """Obtém ou instancia o driver do navegador (Chrome ou Edge) mantendo a aba ativa."""
        if webdriver is None:
            raise RuntimeError("A biblioteca Selenium não está instalada no ambiente.")

        desejado = (browser_name or "auto").lower().strip()

        if self._driver is not None:
            if desejado in ("edge", "chrome") and desejado != self._active_browser:
                self.close()
            else:
                try:
                    handles = self._driver.window_handles
                    if handles:
                        self._driver.switch_to.window(handles[-1])
                        _ = self._driver.title
                        return self._driver
                except Exception:
                    self._driver = None

        tentar_edge_primeiro = (desejado == "edge")

        def _chrome_options() -> ChromeOptions:
            opts = ChromeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--new-window")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-infobars")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)
            opts.add_experimental_option("detach", True)
            return opts

        def _edge_options() -> EdgeOptions:
            opts = EdgeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--new-window")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-infobars")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)
            opts.add_experimental_option("detach", True)
            return opts

        def _try_chrome() -> Any:
            """Tenta inicializar o Chrome via Selenium Manager ou webdriver-manager."""
            opts = _chrome_options()
            try:
                driver = webdriver.Chrome(options=opts)
                self._aplicar_stealth(driver)
                return driver
            except Exception as e1:
                if _WDM_AVAILABLE:
                    try:
                        service = ChromeService(ChromeDriverManager().install())
                        driver = webdriver.Chrome(service=service, options=opts)
                        self._aplicar_stealth(driver)
                        return driver
                    except Exception as e2:
                        raise RuntimeError(f"Chrome falhou com Selenium Manager ({e1}) e webdriver-manager ({e2})")
                raise RuntimeError(f"Chrome falhou: {e1}. Instale webdriver-manager com: pip install webdriver-manager")

        def _try_edge() -> Any:
            """Tenta inicializar o Edge via Selenium Manager ou webdriver-manager."""
            opts = _edge_options()
            try:
                driver = webdriver.Edge(options=opts)
                self._aplicar_stealth(driver)
                return driver
            except Exception as e1:
                if _WDM_AVAILABLE:
                    try:
                        service = EdgeService(EdgeChromiumDriverManager().install())
                        driver = webdriver.Edge(service=service, options=opts)
                        self._aplicar_stealth(driver)
                        return driver
                    except Exception as e2:
                        raise RuntimeError(f"Edge falhou com Selenium Manager ({e1}) e webdriver-manager ({e2})")
                raise RuntimeError(f"Edge falhou: {e1}. Instale webdriver-manager com: pip install webdriver-manager")

        if tentar_edge_primeiro:
            try:
                self._driver = _try_edge()
                self._active_browser = "edge"
                return self._driver
            except Exception as e_edge:
                print(f"[WebAutomation] Falha ao iniciar Edge ({e_edge}). Tentando Chrome...")

        try:
            self._driver = _try_chrome()
            self._active_browser = "chrome"
            return self._driver
        except Exception as e_chrome:
            print(f"[WebAutomation] Chrome falhou ({e_chrome}). Tentando Edge...")

        if not tentar_edge_primeiro:
            try:
                self._driver = _try_edge()
                self._active_browser = "edge"
                return self._driver
            except Exception as e_edge2:
                raise RuntimeError(
                    f"Não foi possível inicializar Chrome nem Edge. "
                    f"Verifique se os navegadores estão instalados e execute: "
                    f"pip install webdriver-manager. Detalhes: {e_edge2}"
                )

        raise RuntimeError("Não foi possível inicializar o navegador via Selenium.")

    def close(self) -> None:
        """Fecha o navegador com segurança e limpa a sessão."""
        if self._driver is not None:
            self._driver.quit()
            self._driver = None


_manager = WebAutomationManager()


def _get_driver(navegador: str = "auto") -> Any:
    """Retorna a instância ativa ou cria uma nova instância do WebDriver."""
    return _manager.get_driver(browser_name=navegador)


def _forcar_primeiro_plano_janela(titulos: list[str] | None = None) -> None:
    """Força de forma inequívoca que a janela do navegador fique maximizada e em primeiro plano na tela do usuário."""
    if titulos is None:
        titulos = ["Google Chrome", "Chrome", "Microsoft Edge", "Edge"]
    import time
    time.sleep(0.4)
    try:
        import pygetwindow as gw
        for t in titulos:
            for w in gw.getWindowsWithTitle(t):
                if w.visible:
                    try:
                        if w.isMinimized:
                            w.restore()
                        w.maximize()
                        w.activate()
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        import ctypes
        import win32gui
        import win32con

        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)

        def _enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd)
                if any(t.lower() in text.lower() for t in titulos):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                    try:
                        win32gui.SetWindowPos(
                            hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
                        )
                        win32gui.SetWindowPos(
                            hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
                        )
                    except Exception:
                        pass
                    win32gui.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)

        win32gui.EnumWindows(_enum_cb, None)
    except Exception:
        pass


def _extrair_links_pagina(driver: Any, max_links: int = 8) -> list[dict[str, str]]:
    """
    Extrai os principais links/resultados clicáveis da aba atual (resultados do Google,
    vídeos do YouTube ou links visíveis da página) para permitir abertura por posição
    ('primeiro link', 'segundo resultado') ou por título parcial.
    """
    try:
        js = """
        const vistos = new Set();
        const saida = [];
        function adicionar(el, textoPreferencial) {
            if (!el || saida.length >= arguments[2]) return;
            const href = el.href || el.getAttribute('href') || '';
            if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return;
            let txt = (textoPreferencial || el.innerText || el.getAttribute('aria-label') || el.title || '').replace(/\\s+/g, ' ').trim();
            if (txt.length < 2) return;
            if (vistos.has(href)) return;
            vistos.add(href);
            saida.push({texto: txt.slice(0, 110), url: href});
        }
        const limite = arguments[0] || 8;
        // 1. Resultados de busca (Google, Bing, DuckDuckGo, YouTube)
        const seletoresPrioritarios = [
            '#search a h3', '#rso a h3', 'a#video-title', 'ytd-video-renderer a#video-title-link',
            'ytd-rich-item-renderer a#video-title-link', 'article h2 a', 'li.b_algo h2 a', 'h3 a', 'h2 a'
        ];
        for (const sel of seletoresPrioritarios) {
            for (const nodo of document.querySelectorAll(sel)) {
                const a = nodo.tagName.toLowerCase() === 'a' ? nodo : nodo.closest('a');
                if (a) adicionar(a, nodo.innerText, limite);
                if (saida.length >= limite) return saida;
            }
        }
        // 2. Links gerais visíveis na página
        for (const a of document.querySelectorAll('a[href]')) {
            adicionar(a, '', limite);
            if (saida.length >= limite) break;
        }
        return saida;
        """
        brutos = driver.execute_script(js, max_links) or []
        links: list[dict[str, str]] = []
        for idx, item in enumerate(brutos, start=1):
            if isinstance(item, dict) and item.get("url"):
                links.append({
                    "indice": str(idx),
                    "texto": str(item.get("texto", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                })
        if links:
            _manager.ultimos_links = links
            return links
        return _manager.ultimos_links
    except Exception:
        return _manager.ultimos_links


def _resumir_links(links: list[dict[str, str]], limite: int = 5) -> str:
    if not links:
        return ""
    partes = [f"{l['indice']}) {l['texto']}" for l in links[:limite] if l.get("texto")]
    if not partes:
        return ""
    return " Links disponíveis na aba: " + " | ".join(partes)


def _registrar_estado_web(
    url: str,
    titulo: str = "",
    links: list[dict[str, str]] | None = None,
    controlavel: bool = True,
) -> None:
    try:
        from core.session_state import registrar_artefato
        cols = [f"{l['indice']}: {l['texto'][:50]}" for l in (links or _manager.ultimos_links)[:5]]
        registrar_artefato("web", url=url, titulo=titulo, colunas=cols)
    except Exception:
        pass
    try:
        from core.overlay import status_overlay
        resumo = (titulo or url)[:48]
        status_overlay(f"● MODO CO-PILOTO WEB: {resumo}", ativo=True, duracao=180.0)
    except Exception:
        pass


def _resolver_indice_ordinal(texto: str) -> int | None:
    """
    Se o texto se referir a uma posição ('primeiro link', '2º resultado', 'terceiro video', '1', 'último'),
    retorna o índice 0-based correspondente (ou -1 para último).
    """
    import re
    import unicodedata

    t = "".join(
        c for c in unicodedata.normalize("NFKD", (texto or "").lower().strip())
        if not unicodedata.combining(c)
    )
    if not t:
        return None

    mapa = [
        (("primeiro", "primeira", "1o", "1a", "link 1", "resultado 1", "video 1", "opcao 1", "item 1"), 0),
        (("segundo", "segunda", "2o", "2a", "link 2", "resultado 2", "video 2", "opcao 2", "item 2"), 1),
        (("terceiro", "terceira", "3o", "3a", "link 3", "resultado 3", "video 3", "opcao 3", "item 3"), 2),
        (("quarto", "quarta", "4o", "4a", "link 4", "resultado 4", "video 4", "opcao 4", "item 4"), 3),
        (("quinto", "quinta", "5o", "5a", "link 5", "resultado 5", "video 5", "opcao 5", "item 5"), 4),
        (("ultimo", "ultima"), -1),
    ]
    for chaves, idx in mapa:
        if any(k in t for k in chaves):
            return idx
    if re.fullmatch(r"[1-9]", t):
        return int(t) - 1
    return None


def navegar_para(url: str, navegador: str = "auto") -> str:
    """Navega para a URL especificada (ou abre um link da página atual) mantendo a sessão ativa."""
    try:
        url_limpa = (url or "").strip()
        if not url_limpa:
            return "Informe a URL ou o link que deseja abrir."

        if (
            not url_limpa.startswith(("http://", "https://", "file://"))
            and "." not in url_limpa
            and not url_limpa.startswith("localhost")
        ):
            if _resolver_indice_ordinal(url_limpa) is not None or _manager._driver is not None or _manager.ultimos_links:
                res_clique = clicar_elemento_web(texto=url_limpa)
                if "sucesso" in res_clique.lower():
                    return res_clique
            return pesquisar_na_web(url_limpa, navegador=navegador)

        if not url_limpa.startswith(("http://", "https://", "file://")):
            url_limpa = f"https://{url_limpa}"

        driver = _manager.get_driver(browser_name=navegador)
        driver.get(url_limpa)
        try:
            driver.maximize_window()
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[-1])
            _forcar_primeiro_plano_janela()
        except Exception:
            pass
        titulo = driver.title or url_limpa
        links = _extrair_links_pagina(driver)
        _registrar_estado_web(getattr(driver, "current_url", url_limpa) or url_limpa, titulo, links)
        return f"Navegador aberto na tela em '{url_limpa}' com sucesso. Título da página: {titulo}.{_resumir_links(links)}"
    except Exception as e:
        try:
            import subprocess
            import sys

            def _abrir_visivel(cmd: list) -> None:
                if sys.platform == "win32":
                    STARTF_USESHOWWINDOW = 0x1
                    SW_SHOW = 5
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= STARTF_USESHOWWINDOW
                    si.wShowWindow = SW_SHOW
                    subprocess.Popen(cmd, startupinfo=si)
                else:
                    subprocess.Popen(cmd)
                _forcar_primeiro_plano_janela()

            nav_lower = (navegador or "").lower()
            if "edge" in nav_lower:
                edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                if os.path.exists(edge_path):
                    _abrir_visivel([edge_path, "--new-window", "--start-maximized", url_limpa])
                    _registrar_estado_web(url_limpa, url_limpa, controlavel=False)
                    return f"Microsoft Edge aberto em '{url_limpa}'."
            if "chrome" in nav_lower or not os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                ]
                for cp in chrome_paths:
                    if os.path.exists(cp):
                        _abrir_visivel([cp, "--new-window", "--start-maximized", url_limpa])
                        _registrar_estado_web(url_limpa, url_limpa, controlavel=False)
                        return f"Google Chrome aberto em '{url_limpa}'."
            os.startfile(url_limpa)
            _registrar_estado_web(url_limpa, url_limpa, controlavel=False)
            return f"Navegador padrão do sistema aberto em '{url_limpa}'."
        except Exception as e2:
            return f"Falha ao navegar para a URL '{url}': {e} / {e2}"


def pesquisar_na_web(termo: str, motor: str = "google", navegador: str = "auto") -> str:
    """
    Pesquisa diretamente por um termo no mecanismo de busca escolhido (Google, YouTube, etc.)
    na aba controlada do navegador co-piloto e extrai os links dos resultados para navegação contínua.
    """
    import subprocess
    try:
        t = (termo or "").strip()
        if not t:
            return "Erro: O termo de pesquisa não pode estar vazio."
        termo_encoded = urllib.parse.quote_plus(t)
        motor_clean = (motor or "google").lower().strip()

        if motor_clean == "youtube":
            url = f"https://www.youtube.com/results?search_query={termo_encoded}"
            origem = "YouTube"
        elif motor_clean == "duckduckgo":
            url = f"https://duckduckgo.com/?q={termo_encoded}"
            origem = "DuckDuckGo"
        elif motor_clean == "bing":
            url = f"https://www.bing.com/search?q={termo_encoded}"
            origem = "Bing"
        else:
            url = f"https://www.google.com/search?q={termo_encoded}"
            origem = "Google"

        try:
            driver = _manager.get_driver(browser_name=navegador)
            driver.get(url)
            try:
                driver.maximize_window()
                if driver.window_handles:
                    driver.switch_to.window(driver.window_handles[-1])
                _forcar_primeiro_plano_janela()
            except Exception:
                pass
            time.sleep(0.5)
            url_atual = (getattr(driver, "current_url", "") or "").lower()
            if "google.com/sorry" in url_atual or "unusual traffic" in (getattr(driver, "page_source", "") or "")[:1500].lower():
                url_alt = f"https://www.bing.com/search?q={termo_encoded}"
                driver.get(url_alt)
                time.sleep(0.5)
            links = _extrair_links_pagina(driver)
            _registrar_estado_web(getattr(driver, "current_url", url), f"{origem}: {t}", links)
            return (
                f"Pesquisa por '{t}' realizada no {origem}. Página de resultados aberta e pronta para navegação."
                f"{_resumir_links(links)}"
            )
        except Exception as e_sel:
            print(f"[pesquisar_na_web] Selenium teve erro ({e_sel}). Acionando abertura nativa...")

        import sys

        def _abrir_visivel_pesquisa(cmd: list) -> None:
            if sys.platform == "win32":
                STARTF_USESHOWWINDOW = 0x1
                SW_SHOW = 5
                si = subprocess.STARTUPINFO()
                si.dwFlags |= STARTF_USESHOWWINDOW
                si.wShowWindow = SW_SHOW
                subprocess.Popen(cmd, startupinfo=si)
            else:
                subprocess.Popen(cmd)
            _forcar_primeiro_plano_janela()
            _registrar_estado_web(url, f"{origem}: {t}", controlavel=False)

        nav_lower = (navegador or "").lower()
        if "edge" in nav_lower:
            edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            if os.path.exists(edge_path):
                _abrir_visivel_pesquisa([edge_path, "--new-window", "--start-maximized", url])
                return f"Microsoft Edge aberto com a pesquisa por '{t}' no {origem}."
        elif "chrome" in nav_lower:
            for cp in [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ]:
                if os.path.exists(cp):
                    _abrir_visivel_pesquisa([cp, "--new-window", "--start-maximized", url])
                    return f"Google Chrome aberto com a pesquisa por '{t}' no {origem}."

        for nav_exe, nav_nome in [
            (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Chrome"),
            (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Chrome"),
            (os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"), "Chrome"),
            (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Edge"),
        ]:
            if os.path.exists(nav_exe):
                _abrir_visivel_pesquisa([nav_exe, "--new-window", "--start-maximized", url])
                return f"{nav_nome} aberto com a pesquisa por '{t}' no {origem}."

        os.startfile(url)
        _registrar_estado_web(url, f"{origem}: {t}", controlavel=False)
        return f"Pesquisa por '{t}' aberta no navegador padrão ({origem})."

    except Exception as e:
        return f"Falha ao realizar pesquisa na web para '{termo}': {e}"


def clicar_elemento_web(seletor: str | None = None, texto: str | None = None) -> str:
    """
    Clica em um link, resultado de pesquisa ('primeiro link', 'segundo resultado', 'primeiro vídeo'),
    botão ou menu na aba web aberta por seletor ou texto visível.
    """
    try:
        driver = _manager.get_driver()
        wait = WebDriverWait(driver, 5)
        alvo_bruto = (texto or seletor or "").strip()

        alvo_lower = alvo_bruto.lower()
        if any(k in alvo_lower for k in ("rolar", "role", "descer", "desça", "desca", "subir", "suba", "voltar pagina", "pagina anterior")):
            return interagir_pagina_web(acao=alvo_bruto)

        if seletor and not texto:
            s_check = seletor.strip()
            eh_seletor_css_xpath = (
                s_check.startswith(("#", ".", "//", "(", "["))
                or any(ch in s_check for ch in ("=", ">", ":", "["))
            )
            if not eh_seletor_css_xpath and _resolver_indice_ordinal(s_check) is not None:
                texto = s_check
                seletor = None

        elemento = None
        href_direto: str | None = None

        idx_ordinal = _resolver_indice_ordinal(texto or seletor or "")
        if idx_ordinal is not None:
            links = _extrair_links_pagina(driver, max_links=12)
            if links:
                escolhido = links[idx_ordinal] if idx_ordinal >= 0 and idx_ordinal < len(links) else (links[-1] if idx_ordinal == -1 else None)
                if escolhido and escolhido.get("url"):
                    url_destino = escolhido["url"]
                    titulo_link = escolhido.get("texto", url_destino)
                    driver.get(url_destino)
                    time.sleep(0.4)
                    if driver.window_handles:
                        driver.switch_to.window(driver.window_handles[-1])
                    novos_links = _extrair_links_pagina(driver)
                    titulo_pag = getattr(driver, "title", "") or titulo_link
                    _registrar_estado_web(getattr(driver, "current_url", url_destino), titulo_pag, novos_links)
                    return f"Link '{titulo_link}' aberto com sucesso na aba atual ({url_destino}). Título: {titulo_pag}."

        if seletor:
            s = seletor.strip()
            try:
                if s.startswith("//") or s.startswith("("):
                    elemento = wait.until(EC.element_to_be_clickable((By.XPATH, s)))
                else:
                    elemento = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, s)))
            except Exception:
                if not texto:
                    texto = s

        if elemento is None and texto:
            t = texto.strip()
            import re
            t_limpo = re.sub(
                r"^(abra o |abra a |abrir o |abrir a |abra esse |acesse o |acesse a |acesse esse |acessar o |acessar esse |clique no |clique na |clique em |entrar no |entre no |esse |este |link do |link da |site do |site da |link |botao |botão |site |resultado |video |vídeo )+",
                "",
                t,
                flags=re.IGNORECASE,
            ).strip() or t

            links_atuais = _manager.ultimos_links or _extrair_links_pagina(driver, max_links=15)
            for l in links_atuais:
                if t_limpo.lower() in l.get("texto", "").lower() or t_limpo.lower() in l.get("url", "").lower():
                    href_direto = l.get("url")
                    break

            js_find = """
            const query = (arguments[0] || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().trim();
            if (!query) return null;
            const candidatos = Array.from(document.querySelectorAll(
                'a, button, [role="button"], input[type="submit"], input[type="button"], h3, h2, h1, span, div[ tabindex ]'
            ));
            let melhor = null;
            let menorTam = 999999;
            for (const el of candidatos) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const bruto = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').replace(/\\s+/g, ' ').trim();
                const norm = bruto.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
                if (norm && norm.includes(query)) {
                    const clicavel = el.closest('a, button, [role="button"]') || el;
                    if (norm === query) return clicavel;
                    if (norm.length < menorTam) {
                        menorTam = norm.length;
                        melhor = clicavel;
                    }
                }
            }
            return melhor;
            """
            try:
                elemento = driver.execute_script(js_find, t_limpo)
            except Exception:
                elemento = None

            if elemento is None and href_direto:
                driver.get(href_direto)
                try:
                    driver.maximize_window()
                    _forcar_primeiro_plano_janela()
                except Exception:
                    pass
                time.sleep(0.4)
                novos_links = _extrair_links_pagina(driver)
                _registrar_estado_web(getattr(driver, "current_url", href_direto), getattr(driver, "title", ""), novos_links)
                return f"Elemento/link '{t_limpo}' aberto com sucesso em '{href_direto}'."

        if elemento is None:
            url_corrente = (getattr(driver, "current_url", "") or "").lower()
            if (not url_corrente or url_corrente.startswith(("data:", "about:blank"))) and texto:
                return pesquisar_na_web(texto.strip())
            return f"Elemento não encontrado na página para o alvo (seletor='{seletor}', texto='{texto}')."

        handles_antes = list(getattr(driver, "window_handles", []) or [])
        url_antes = getattr(driver, "current_url", "")
        if not href_direto:
            try:
                href_direto = elemento.get_attribute("href")
            except Exception:
                href_direto = None

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
        time.sleep(0.15)
        try:
            elemento.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", elemento)
            except Exception:
                if href_direto and href_direto.startswith(("http://", "https://", "file://")):
                    driver.get(href_direto)

        time.sleep(0.35)
        handles_depois = list(getattr(driver, "window_handles", []) or [])
        if len(handles_depois) > len(handles_antes):
            driver.switch_to.window(handles_depois[-1])
        elif (
            href_direto
            and href_direto.startswith(("http://", "https://"))
            and getattr(driver, "current_url", "") == url_antes
        ):
            driver.get(href_direto)

        novos_links = _extrair_links_pagina(driver)
        url_final = getattr(driver, "current_url", "")
        titulo_final = getattr(driver, "title", "")
        _registrar_estado_web(url_final, titulo_final, novos_links)
        return f"Elemento clicado com sucesso (alvo: '{texto or seletor}'). Página atual: '{titulo_final}' ({url_final})."
    except Exception as e:
        return f"Falha ao clicar no elemento web: {e}"


def digitar_campo_web(texto: str, seletor: str | None = None, submeter: bool = True) -> str:
    """Digita texto em um campo de entrada ou barra de pesquisa na página web atual."""
    try:
        if seletor and texto and texto.strip().startswith(("#", ".", "//", "[")) and not seletor.strip().startswith(("#", ".", "//", "[")):
            texto, seletor = seletor, texto

        driver = _manager.get_driver()
        wait = WebDriverWait(driver, 5)
        campo = None

        if seletor:
            s = seletor.strip()
            if s.startswith("//") or s.startswith("("):
                campo = wait.until(EC.visibility_of_element_to_be_clickable((By.XPATH, s)))
            else:
                campo = wait.until(EC.visibility_of_element_to_be_clickable((By.CSS_SELECTOR, s)))
        else:
            try:
                ativo = driver.switch_to.active_element
                tag = (ativo.tag_name or "").lower() if ativo else ""
                if tag in ("input", "textarea") or (ativo and ativo.get_attribute("isContentEditable") == "true"):
                    campo = ativo
            except Exception:
                campo = None

            if campo is None:
                seletores_busca = [
                    "textarea[name='q']",
                    "input[name='q']",
                    "input[name='search_query']",
                    "input[type='search']",
                    "input[type='text']",
                    "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox'])",
                    "textarea",
                ]
                for sel in seletores_busca:
                    try:
                        candidatos = driver.find_elements(By.CSS_SELECTOR, sel)
                        for c in candidatos:
                            if c.is_displayed() and c.is_enabled():
                                campo = c
                                break
                        if campo is not None:
                            break
                    except Exception:
                        continue

        if campo is None:
            return "Nenhum campo de texto editável foi encontrado na página atual."

        try:
            campo.click()
        except Exception:
            pass
        try:
            campo.clear()
        except Exception:
            pass
        campo.send_keys(texto)

        if submeter:
            campo.send_keys(Keys.ENTER)
            time.sleep(0.4)
            links = _extrair_links_pagina(driver)
            _registrar_estado_web(getattr(driver, "current_url", ""), getattr(driver, "title", ""), links)
            return f"Texto digitado no campo e enviado com Enter com sucesso: '{texto}'."

        return f"Texto preenchido no campo com sucesso: '{texto}'."
    except Exception as e:
        return f"Falha ao digitar no campo web: {e}"


def interagir_pagina_web(acao: str, valor: str | None = None) -> str:
    """
    Executa ações completas de navegação e controle na aba aberta do navegador:
    rolar para baixo/cima, ir para topo/fim, voltar, avançar, atualizar, trocar/fechar aba ou abrir um link.
    """
    try:
        driver = _manager.get_driver()
        a = (acao or "").lower().strip()
        v = (valor or "").strip()

        if any(k in a for k in ("baixo", "descer", "desça", "desca", "scroll down")):
            driver.execute_script("window.scrollBy({top: 680, behavior: 'smooth'});")
            return "Página rolada para baixo com sucesso."
        if any(k in a for k in ("cima", "subir", "suba", "scroll up")):
            driver.execute_script("window.scrollBy({top: -680, behavior: 'smooth'});")
            return "Página rolada para cima com sucesso."
        if "topo" in a or "inicio" in a or "início" in a:
            driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
            return "Página posicionada no topo."
        if "fim" in a or "final" in a or "rodape" in a or "rodapé" in a:
            driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});")
            return "Página rolada até o final."
        if any(k in a for k in ("voltar", "anterior", "back")):
            driver.back()
            time.sleep(0.3)
            links = _extrair_links_pagina(driver)
            _registrar_estado_web(getattr(driver, "current_url", ""), getattr(driver, "title", ""), links)
            return f"Retornou para a página anterior: '{getattr(driver, 'title', '')}'."
        if any(k in a for k in ("avancar", "avançar", "proxima", "próxima", "forward")):
            driver.forward()
            time.sleep(0.3)
            links = _extrair_links_pagina(driver)
            _registrar_estado_web(getattr(driver, "current_url", ""), getattr(driver, "title", ""), links)
            return f"Avançou para a página: '{getattr(driver, 'title', '')}'."
        if any(k in a for k in ("atualizar", "recarregar", "refresh", "f5")):
            driver.refresh()
            time.sleep(0.3)
            return "Página recarregada com sucesso."
        if "fechar_aba" in a or "fechar aba" in a:
            handles = list(driver.window_handles)
            if len(handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
                _registrar_estado_web(driver.current_url, driver.title, _extrair_links_pagina(driver))
                return f"Aba fechada. Aba ativa agora: '{getattr(driver, 'title', '')}'."
            return fechar_navegador()
        if "listar" in a or "links" in a:
            links = _extrair_links_pagina(driver, max_links=10)
            return _resumir_links(links, limite=10) or "Nenhum link encontrado na página atual."
        if v:
            return clicar_elemento_web(texto=v)
        return clicar_elemento_web(texto=acao)
    except Exception as e:
        return f"Falha ao interagir com a página web: {e}"


def ler_conteudo_pagina(seletor: str | None = None, max_caracteres: int = 1200) -> str:
    """Extrai e lê o conteúdo textual da página web aberta para leitura ou síntese."""
    try:
        driver = _manager.get_driver()
        if seletor:
            elemento = driver.find_element(By.CSS_SELECTOR, seletor)
            texto_puro = elemento.text or ""
        else:
            texto_puro = driver.find_element(By.TAG_NAME, "body").text or ""

        linhas = [linha.strip() for linha in texto_puro.splitlines() if linha.strip()]
        conteudo = " ".join(linhas)

        if len(conteudo) > max_caracteres:
            conteudo = conteudo[:max_caracteres] + " [...]"

        if not conteudo:
            return "Nenhum texto legível foi encontrado na página atual."

        return f"Conteúdo da página (título: {driver.title}):\n{conteudo}"
    except Exception as e:
        return f"Falha ao ler conteúdo da página web: {e}"


def capturar_tela_web(nome_arquivo: str | None = None) -> str:
    """Captura uma imagem da visualização atual do navegador e salva na pasta screenshots/."""
    try:
        driver = _manager.get_driver()
        pasta = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
        os.makedirs(pasta, exist_ok=True)

        nome = nome_arquivo or f"screenshot_web_{int(time.time())}.png"
        if not nome.endswith(".png"):
            nome = f"{nome}.png"

        caminho_final = os.path.join(pasta, nome)
        driver.save_screenshot(caminho_final)
        return f"Captura da página web salva com sucesso em: {caminho_final}"
    except Exception as e:
        return f"Falha ao capturar tela da página web: {e}"


def fechar_navegador() -> str:
    """Fecha a sessão ativa do navegador web."""
    try:
        _manager.close()
        try:
            from core.overlay import status_overlay
            status_overlay("", ativo=False, duracao=0.0)
        except Exception:
            pass
        return "Navegador web encerrado com sucesso."
    except Exception as e:
        return f"Erro ao fechar o navegador web: {e}"


WEB_TOOLS_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "navegar_para",
            "description": "Navega diretamente para um site ou endereço web no navegador (ex: 'youtube.com', 'google.com', 'globo.com').",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Endereço ou domínio do site a ser acessado (ex: 'https://github.com')"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_na_web",
            "description": "Faz uma busca no Google, YouTube, DuckDuckGo ou Bing e abre a página de resultados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {
                        "type": "string",
                        "description": "O que você quer pesquisar (termo, pergunta ou assunto)"
                    },
                    "motor": {
                        "type": "string",
                        "enum": ["google", "youtube", "duckduckgo", "bing"],
                        "description": "Mecanismo de busca (padrão: 'google')"
                    }
                },
                "required": ["termo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clicar_elemento_web",
            "description": (
                "Abre um link ou resultado da página web aberta (ex: 'primeiro link', 'segundo resultado', "
                "'primeiro vídeo') ou clica em qualquer botão, menu ou item pelo texto visível ou seletor."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Texto visível do link/botão ou posição ordinal (ex: 'primeiro link', 'segundo resultado', 'Entrar', 'Vídeos')"
                    },
                    "seletor": {
                        "type": "string",
                        "description": "Seletor CSS ou XPath opcional do elemento"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "interagir_pagina_web",
            "description": (
                "Controla e navega dentro da aba aberta do navegador: rolar para baixo/cima, "
                "ir ao topo/fim, voltar à página anterior, avançar, atualizar, listar links ou fechar aba."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "description": "Ação a executar na aba: 'rolar_baixo', 'rolar_cima', 'topo', 'fim', 'voltar', 'avancar', 'atualizar', 'fechar_aba', 'listar_links' ou 'abrir_link'"
                    },
                    "valor": {
                        "type": "string",
                        "description": "Alvo opcional quando a ação for 'abrir_link' ou 'clicar' (ex: 'primeiro link')"
                    }
                },
                "required": ["acao"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "digitar_campo_web",
            "description": "Preenche um campo de texto, formulário ou barra de busca na página web aberta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "O texto a ser digitado"
                    },
                    "seletor": {
                        "type": "string",
                        "description": "Seletor CSS do campo (opcional, digita no elemento focado)"
                    },
                    "submeter": {
                        "type": "boolean",
                        "description": "Se deve teclar Enter ao final (padrão: true)"
                    }
                },
                "required": ["texto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_conteudo_pagina",
            "description": "Lê o conteúdo escrito da página web atual para responder perguntas ou sintetizar a informação em voz alta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seletor": {
                        "type": "string",
                        "description": "Seletor CSS opcional de uma parte específica da página"
                    },
                    "max_caracteres": {
                        "type": "integer",
                        "description": "Limite máximo de caracteres a ler (padrão: 1200)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capturar_tela_web",
            "description": "Tira um print/screenshot da janela da página web aberta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_arquivo": {
                        "type": "string",
                        "description": "Nome do arquivo (ex: 'resultado.png')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fechar_navegador",
            "description": "Fecha a janela do navegador web controlada pela assistente.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
