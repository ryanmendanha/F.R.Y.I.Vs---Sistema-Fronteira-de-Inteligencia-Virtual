"""
Módulo de Visão Computacional e OCR para F.R.Y.I.Vs.
Utiliza OpenCV-Python e PyTesseract para localizar botões na tela visualmente
e extrair textos de imagens, capturas de tela e sistemas antigos.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Final
from pydantic import BaseModel, Field

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

_TESSERACT_COMMON_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")
]


def _configurar_tesseract() -> bool:
    """Configura o executável do tesseract se estiver instalado no Windows."""
    if pytesseract is None:
        return False

    if shutil.which("tesseract"):
        return True

    for caminho in _TESSERACT_COMMON_PATHS:
        if os.path.exists(caminho):
            pytesseract.pytesseract.tesseract_cmd = caminho
            return True

    return False


class LocalizarImagemParams(BaseModel):
    imagem_alvo: str = Field(
        ...,
        description="Nome ou caminho do arquivo da imagem de referência do botão ou ícone a ser clicado"
    )
    confianca: float = Field(
        default=0.8,
        description="Grau de confiança de similaridade visual (0.1 a 1.0, padrão: 0.8)"
    )


class LerTextoTelaParams(BaseModel):
    regiao: list[int] | None = Field(
        default=None,
        description="Região opcional na tela [x, y, largura, altura]. Se omitido, lê a tela inteira."
    )


def localizar_e_clicar_imagem(imagem_alvo: str, confianca: float = 0.8) -> str:
    """
    Localiza visualmente um botão, ícone ou imagem na tela usando OpenCV e clica nele com PyAutoGUI.
    """
    if pyautogui is None or cv2 is None:
        return "Erro: As bibliotecas PyAutoGUI e OpenCV são necessárias para busca visual de botões."

    try:
        caminho = imagem_alvo
        if not os.path.isabs(caminho):
            pastas_teste = [
                os.path.abspath(imagem_alvo),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots", imagem_alvo),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), imagem_alvo),
            ]
            for p in pastas_teste:
                if os.path.exists(p):
                    caminho = p
                    break

        if not os.path.exists(caminho):
            return f"Arquivo de imagem de referência não encontrado: '{imagem_alvo}'."

        ponto = pyautogui.locateCenterOnScreen(caminho, confidence=confianca)
        if ponto is None:
            return f"O elemento visual '{os.path.basename(caminho)}' não foi encontrado na tela com confiança {confianca}."

        x, y = ponto
        pyautogui.click(x, y)
        return f"Botão visual localizado com OpenCV e clicado nas coordenadas X={x}, Y={y}."
    except Exception as e:
        return f"Falha na busca visual do botão na tela: {e}"


def ler_texto_da_tela(regiao: list[int] | None = None) -> str:
    """
    Captura a tela (ou região específica), processa a imagem com OpenCV e extrai o texto com PyTesseract (OCR).
    """
    if pyautogui is None or pytesseract is None:
        return "Erro: PyAutoGUI e PyTesseract são necessários para extração de texto da tela."

    if not _configurar_tesseract():
        return (
            "O motor Tesseract-OCR não foi encontrado no sistema operacional. "
            "Para leitura OCR de textos na tela, por favor instale o instalador do Tesseract para Windows em 'C:\\Program Files\\Tesseract-OCR'."
        )

    try:
        regiao_tuple = tuple(regiao) if (regiao and len(regiao) == 4) else None
        screenshot = pyautogui.screenshot(region=regiao_tuple)

        img_np = np.array(screenshot)
        img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        texto_extraido = pytesseract.image_to_string(processed, lang="por+eng")
        texto_limpo = "\n".join([line.strip() for line in texto_extraido.splitlines() if line.strip()])

        if not texto_limpo:
            return "Nenhum texto legível foi identificado na área capturada da tela."

        if len(texto_limpo) > 1000:
            texto_limpo = texto_limpo[:1000] + " [...]"

        return f"Texto detectado na tela via OCR:\n{texto_limpo}"
    except Exception as e:
        return f"Falha ao realizar OCR na tela: {e}"


VISUAL_OCR_SCHEMAS: Final[list[dict[str, Any]]] = [
    {
        "type": "function",
        "function": {
            "name": "localizar_e_clicar_imagem",
            "description": "Localiza visualmente um botão, ícone ou imagem na tela usando OpenCV e clica nele.",
            "parameters": {
                "type": "object",
                "properties": {
                    "imagem_alvo": {
                        "type": "string",
                        "description": "Nome ou caminho do arquivo da imagem de referência (ex: 'botao_enviar.png')"
                    },
                    "confianca": {
                        "type": "number",
                        "description": "Grau de similaridade visual entre 0.1 e 1.0 (padrão: 0.8)"
                    }
                },
                "required": ["imagem_alvo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ler_texto_da_tela",
            "description": "Lê palavras e textos escritos na tela ou em fotos utilizando OCR (Reconhecimento Óptico de Caracteres).",
            "parameters": {
                "type": "object",
                "properties": {
                    "regiao": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Coordenadas opcionais [x, y, largura, altura]. Se omitido, lê a tela inteira."
                    }
                }
            }
        }
    }
]
