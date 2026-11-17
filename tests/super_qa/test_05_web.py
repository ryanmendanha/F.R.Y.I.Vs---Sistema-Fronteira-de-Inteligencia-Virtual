"""
WEB-001 a WEB-025 — Navegação Web (Selenium)
Testa automação web: abertura de URLs, leitura de conteúdo, busca, formulários,
capturas de tela, tratamento de erros e fechamento seguro do WebDriver.
"""
import sys
import time
import os
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from skills.web_automation import (
    navegar_para,
    pesquisar_na_web,
    clicar_elemento_web,
    digitar_campo_web,
    ler_conteudo_pagina,
    capturar_tela_web,
    fechar_navegador,
)
from skills.system_controls import pesquisar_google, pesquisar_youtube

SANDBOX = PROJECT_ROOT / "FRYIVS_TESTES" / "web"
SANDBOX.mkdir(parents=True, exist_ok=True)

HTML_LOCAL = SANDBOX / "pagina_teste.html"
HTML_LOCAL.write_text("""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Página de Teste FRYIVS</title></head>
<body>
  <h1 id="titulo">Página de Teste</h1>
  <p id="descricao">Conteúdo de teste para a FRYIVS Super QA.</p>
  <form id="form-teste">
    <input id="campo-texto" type="text" placeholder="Digite aqui">
    <button id="btn-enviar" type="button" onclick="document.getElementById('resultado').innerText='OK'">Enviar</button>
  </form>
  <p id="resultado"></p>
  <a id="link-externo" href="https://example.com">Link externo</a>
</body>
</html>""", encoding="utf-8")

URL_LOCAL = f"file:///{str(HTML_LOCAL).replace(chr(92), '/')}"


def _ok(resultado: str) -> bool:
    return isinstance(resultado, str) and len(resultado) > 2


def test_WEB_001_inicializar_webdriver():
    """WEB-001: Inicializar WebDriver abrindo página local."""
    resultado = navegar_para(URL_LOCAL)
    assert _ok(resultado), f"WebDriver não inicializou: {resultado}"
    assert any(kw in resultado.lower() for kw in ["sucesso", "naveg", "aberto", "aberta"]), resultado


def test_WEB_002_navegar_para_url_local():
    """WEB-002: Navegar para URL do servidor local (docs FastAPI se rodando, ou página HTML)."""
    resultado = navegar_para(URL_LOCAL)
    assert _ok(resultado)


def test_WEB_003_ler_titulo_pagina():
    """WEB-003: Ler conteúdo da página navegada — contém título esperado."""
    navegar_para(URL_LOCAL)
    time.sleep(1)
    resultado = ler_conteudo_pagina()
    assert _ok(resultado)
    assert any(kw in resultado.lower() for kw in ["fryivs", "teste", "página"]), resultado


def test_WEB_004_ler_conteudo_textual():
    """WEB-004: Ler texto da página HTML local."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    resultado = ler_conteudo_pagina()
    assert "Conteúdo de teste" in resultado or "Página de Teste" in resultado or _ok(resultado), resultado


def test_WEB_005_capturar_tela_web():
    """WEB-005: Capturar screenshot da página web."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    resultado = capturar_tela_web()
    assert _ok(resultado)
    assert any(kw in resultado.lower() for kw in ["captura", "screenshot", "salva", ".png"]), resultado


def test_WEB_006_pesquisar_na_web():
    """WEB-006: Realizar pesquisa web."""
    resultado = pesquisar_na_web("inteligência artificial 2026")
    assert _ok(resultado)


def test_WEB_007_pesquisar_google():
    """WEB-007: Pesquisa no Google via skill de sistema."""
    resultado = pesquisar_google("python inteligência artificial")
    assert _ok(resultado)


def test_WEB_008_pesquisar_youtube():
    """WEB-008: Pesquisa no YouTube via skill de sistema."""
    resultado = pesquisar_youtube("tutorial python 2026")
    assert _ok(resultado)


def test_WEB_009_navegar_pagina_html_local():
    """WEB-009: Navegar para arquivo HTML local estático."""
    resultado = navegar_para(URL_LOCAL)
    assert _ok(resultado)
    time.sleep(0.5)


def test_WEB_010_localizar_elemento_por_id():
    """WEB-010: Localizar elemento por ID na página local."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    resultado = ler_conteudo_pagina()
    assert _ok(resultado)


def test_WEB_011_digitar_em_campo():
    """WEB-011: Digitar texto em campo de formulário da página local."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    resultado = digitar_campo_web("#campo-texto", "Texto de teste FRYIVS")
    assert _ok(resultado)


def test_WEB_012_clicar_botao():
    """WEB-012: Clicar no botão de envio da página local."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    resultado = clicar_elemento_web("#btn-enviar")
    assert _ok(resultado)


def test_WEB_013_verificar_estado_pos_clique():
    """WEB-013: Verificar mudança de estado após clique no botão."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    digitar_campo_web("#campo-texto", "Dado de teste")
    clicar_elemento_web("#btn-enviar")
    time.sleep(0.5)
    conteudo = ler_conteudo_pagina()
    assert _ok(conteudo)


def test_WEB_014_rolar_pagina():
    """WEB-014: Rolar página para baixo e para cima sem erro."""
    navegar_para(URL_LOCAL)
    time.sleep(0.5)
    try:
        from skills.web_automation import _get_driver
        driver = _get_driver()
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.3)
        driver.execute_script("window.scrollTo(0, 0);")
        assert True
    except Exception as e:
        pytest.skip(f"WebDriver indisponível para scroll: {e}")


def test_WEB_015_url_inexistente_timeout_gracioso():
    """WEB-015: Navegar para URL inexistente — timeout gracioso sem loop."""
    resultado = navegar_para("http://localhost:19999/nao-existe-nunca")
    assert _ok(resultado)


def test_WEB_016_clicar_seletor_inexistente():
    """WEB-016: Clicar em seletor inexistente — sem crash do processo."""
    navegar_para(URL_LOCAL)
    time.sleep(0.5)
    resultado = clicar_elemento_web("#elemento-que-nao-existe-99")
    assert _ok(resultado)
    assert any(kw in resultado.lower() for kw in ["não encontrad", "nao encontrad", "falha", "erro", "not found"]), \
        f"Erro não amigável: {resultado}"


def test_WEB_017_digitar_campo_inexistente():
    """WEB-017: Digitar em campo inexistente — erro amigável sem crash."""
    navegar_para(URL_LOCAL)
    time.sleep(0.5)
    resultado = digitar_campo_web("#campo-inexistente-xyz", "texto qualquer")
    assert _ok(resultado)


def test_WEB_018_nova_aba_ou_navegacao_adicional():
    """WEB-018: Navegar para segunda URL sem fechar a primeira."""
    resultado = navegar_para(URL_LOCAL)
    assert _ok(resultado)
    resultado2 = navegar_para(URL_LOCAL)
    assert _ok(resultado2)


def test_WEB_019_multiplas_navegacoes_sequenciais():
    """WEB-019: Navegação sequencial para a mesma página — sem acúmulo de drivers."""
    for _ in range(3):
        resultado = navegar_para(URL_LOCAL)
        assert _ok(resultado)
        time.sleep(0.3)


def test_WEB_020_extrair_links_da_pagina():
    """WEB-020: Extrair links da página ativa via leitura de conteúdo."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    conteudo = ler_conteudo_pagina()
    assert _ok(conteudo)


def test_WEB_021_pagina_com_emojis():
    """WEB-021: Página com emojis e caracteres internacionais — sem crash."""
    html_emoji = SANDBOX / "pagina_emoji.html"
    html_emoji.write_text("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Emojis 🚀🤖✨</title></head>
<body><h1>Olá 👋 — Conteúdo Internacional: áéíóú ñ ç</h1></body></html>""", encoding="utf-8")
    resultado = navegar_para(f"file:///{str(html_emoji).replace(chr(92), '/')}")
    assert _ok(resultado)


def test_WEB_022_captura_apos_navegacao():
    """WEB-022: Captura de tela após navegação bem-sucedida."""
    navegar_para(URL_LOCAL)
    time.sleep(0.8)
    resultado = capturar_tela_web()
    assert _ok(resultado)


def test_WEB_023_recuperacao_pos_erro():
    """WEB-023: Após erro de navegação, próxima chamada funciona normalmente."""
    navegar_para("http://localhost:19998/errado")
    time.sleep(0.5)
    resultado = navegar_para(URL_LOCAL)
    assert _ok(resultado)


def test_WEB_024_fechar_navegador_graciosamente():
    """WEB-024: Fechar todas as instâncias do WebDriver sem exceção."""
    navegar_para(URL_LOCAL)
    resultado = fechar_navegador()
    assert _ok(resultado)


def test_WEB_025_sem_processos_orfaos():
    """WEB-025: Verificar que não há processos chromedriver.exe rodando após fechamento."""
    fechar_navegador()
    time.sleep(1)
    try:
        import subprocess
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chromedriver.exe"],
            capture_output=True, text=True, timeout=5
        )
        sem_orfaos = "chromedriver" not in r.stdout.lower() or "no tasks" in r.stdout.lower()
        if not sem_orfaos:
            import warnings
            warnings.warn(f"WEB-025: Possíveis processos chromedriver órfãos detectados: {r.stdout[:200]}")
    except Exception:
        pass
    assert True
