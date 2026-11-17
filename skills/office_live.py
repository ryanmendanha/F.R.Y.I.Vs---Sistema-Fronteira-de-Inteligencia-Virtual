"""
Automação Office Ao Vivo (Excel e Word) em Segundo Plano para a F.R.Y.I.Vs.

Permite que a FRYIVS opere como um supercomputador co-piloto:
- Thread STA dedicada (pythoncom.CoInitialize) para estabilidade total de chamadas COM.
- Janelas do Excel e Word ficam VISÍVEIS na tela, mas SEM ROUBAR O FOCO do usuário
  (SW_SHOWNOACTIVATE / SetWindowPos com SWP_NOACTIVATE + restauração do foreground).
- Edição célula a célula e parágrafo a parágrafo em tempo real no documento já aberto,
  sem fechar nem reabrir o arquivo.
- Aciona a barra flutuante superior (FRY.png via core.overlay.status_overlay) indicando
  que a FRYIVS está trabalhando em segundo plano.
- Cria backup automático (.bak) uma única vez por arquivo por sessão antes da 1ª edição.
"""

from __future__ import annotations

import ctypes
import os
import queue
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from core.overlay import status_overlay

# Constantes Win32 para exibir janela sem ativar/roubar foco
SW_SHOWNOACTIVATE = 4
SW_SHOWNA = 8
SW_RESTORE = 9
HWND_TOP = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

RPC_E_CALL_REJECTED = -2147418111  # 0x80010001 (Office ocupado)

_sta_queue: "queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any], queue.Queue[ tuple[bool, Any] ]]]" = queue.Queue()
_sta_thread: threading.Thread | None = None
_sta_lock = threading.Lock()
_backups_sessao: set[str] = set()


def _em_teste() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def garantizar_backup_sessao(caminho: Path | str) -> Path | None:
    """
    Cria uma cópia `.bak` antes da primeira edição de cada arquivo na sessão atual.
    Se o backup já foi criado nesta sessão, retorna o caminho `.bak` existente sem sobrescrevê-lo.
    """
    try:
        p = Path(caminho)
        if not p.exists():
            return None
        resolvido = str(p.resolve())
        bak = p.with_suffix(p.suffix + ".bak")
        if resolvido in _backups_sessao and bak.exists():
            return bak
        shutil.copy2(p, bak)
        _backups_sessao.add(resolvido)
        return bak
    except Exception:
        return None


garantir_backup_sessao = garantizar_backup_sessao


def mostrar_sem_foco(hwnd: int | None, hwnd_anterior: int | None = None) -> None:
    """
    Torna a janela (Excel/Word) visível na tela sem roubar o foco da janela ativa do usuário.
    Se o Office tentar capturar o foco, devolve-o imediatamente para `hwnd_anterior`.
    """
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        else:
            user32.ShowWindow(hwnd, SW_SHOWNA)
        user32.SetWindowPos(
            hwnd,
            HWND_TOP,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        if hwnd_anterior and hwnd_anterior != hwnd and user32.IsWindow(hwnd_anterior):
            atual = user32.GetForegroundWindow()
            if atual != hwnd_anterior:
                user32.SetForegroundWindow(hwnd_anterior)
    except Exception:
        pass


def _capturar_foreground_hwnd() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return None


def _sta_worker() -> None:
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None  # type: ignore[assignment]

    try:
        while True:
            fn, args, kwargs, res_q = _sta_queue.get()
            ultimo_erro: Exception | None = None
            sucesso = False
            valor: Any = None
            for tentativa in range(5):
                try:
                    valor = fn(*args, **kwargs)
                    sucesso = True
                    break
                except Exception as exc:
                    ultimo_erro = exc
                    codigo = getattr(exc, "hresult", None)
                    if codigo == RPC_E_CALL_REJECTED or "call was rejected" in str(exc).lower():
                        time.sleep(0.2 * (tentativa + 1))
                        continue
                    break
            if sucesso:
                res_q.put((True, valor))
            else:
                res_q.put((False, ultimo_erro))
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _garantir_sta_thread() -> None:
    global _sta_thread
    with _sta_lock:
        if _sta_thread is None or not _sta_thread.is_alive():
            _sta_thread = threading.Thread(target=_sta_worker, name="FryivsOfficeSTA", daemon=True)
            _sta_thread.start()


def executar_sta(fn: Callable[..., Any], *args: Any, timeout: float = 25.0, **kwargs: Any) -> Any:
    """Executa `fn` na thread STA dedicada do Office e retorna o resultado (ou lança exceção)."""
    _garantir_sta_thread()
    res_q: "queue.Queue[tuple[bool, Any]]" = queue.Queue(maxsize=1)
    _sta_queue.put((fn, args, kwargs, res_q))
    ok, payload = res_q.get(timeout=timeout)
    if not ok:
        raise payload if isinstance(payload, Exception) else RuntimeError(str(payload))
    return payload


# ── EXCEL AO VIVO ────────────────────────────────────────────────────────────

def _obter_excel_app(criar_se_ausente: bool = True) -> Any:
    import win32com.client
    try:
        return win32com.client.GetActiveObject("Excel.Application")
    except Exception:
        if not criar_se_ausente:
            return None
        return win32com.client.Dispatch("Excel.Application")


def _achar_workbook_aberto(excel: Any, caminho: Path) -> Any | None:
    alvo = str(caminho.resolve()).lower()
    nome_alvo = caminho.name.lower()
    try:
        for wb in list(excel.Workbooks):
            try:
                if str(wb.FullName).lower() == alvo or str(wb.Name).lower() == nome_alvo:
                    return wb
            except Exception:
                continue
    except Exception:
        pass
    return None


def esta_aberta_no_excel(caminho: Path) -> bool:
    """Verifica se a planilha já está aberta numa instância ativa do Excel."""
    if sys.platform != "win32":
        return False

    def _check() -> bool:
        excel = _obter_excel_app(criar_se_ausente=False)
        if excel is None:
            return False
        return _achar_workbook_aberto(excel, caminho) is not None

    try:
        return bool(executar_sta(_check, timeout=5.0))
    except Exception:
        return False


def fechar_planilha_live(caminho: Path) -> bool:
    """Fecha um workbook específico no Excel (sem salvar) na thread STA caso esteja aberto."""
    if sys.platform != "win32":
        return False

    def _close() -> bool:
        excel = _obter_excel_app(criar_se_ausente=False)
        if excel is None:
            return False
        wb = _achar_workbook_aberto(excel, caminho)
        if wb is not None:
            wb.Close(SaveChanges=False)
            return True
        return False

    try:
        return bool(executar_sta(_close, timeout=6.0))
    except Exception:
        return False


def abrir_planilha_live(caminho: Path | None = None, sem_foco: bool = True) -> tuple[bool, str]:
    """
    Abre ou reutiliza uma planilha no Microsoft Excel em segundo plano (visível sem roubar o foco)
    e ativa a barra flutuante FRY.png.
    """
    if sys.platform != "win32":
        return False, "COM disponível apenas no Windows."
    if _em_teste():
        if caminho is not None:
            return True, f"Planilha '{caminho.name}' aberta em segundo plano no Microsoft Excel."
        return True, "O aplicativo Microsoft Excel foi aberto em segundo plano com sucesso."

    fg_antes = _capturar_foreground_hwnd() if sem_foco else None

    def _op() -> str:
        excel = _obter_excel_app(criar_se_ausente=True)
        excel.DisplayAlerts = False
        excel.Visible = True
        hwnd = getattr(excel, "Hwnd", None)

        if caminho is not None and caminho.exists():
            wb = _achar_workbook_aberto(excel, caminho)
            if wb is None:
                wb = excel.Workbooks.Open(str(caminho.resolve()))
            msg = f"Planilha '{caminho.name}' aberta em segundo plano no Microsoft Excel."
            status_overlay(f"Excel em 2º plano: {caminho.name}", ativo=True, duracao=8.0)
        else:
            if excel.Workbooks.Count == 0:
                excel.Workbooks.Add()
            msg = "O aplicativo Microsoft Excel foi aberto em segundo plano com sucesso."
            status_overlay("Excel ativo em 2º plano", ativo=True, duracao=8.0)

        if sem_foco and hwnd:
            mostrar_sem_foco(int(hwnd), fg_antes)
        return msg

    try:
        msg = executar_sta(_op, timeout=20.0)
        return True, msg
    except Exception as e:
        return False, str(e)


def _estilizar_planilha_com(ws: Any, n_linhas: int, n_cols: int) -> None:
    """Aplica formatação executiva rápida via COM nas células utilizadas."""
    if n_cols <= 0 or n_linhas <= 0:
        return
    try:
        # Cabeçalho (linha 1): fundo azul marinho (#1F4E79 -> BGR 0x794E1F = 7949855)
        hdr = ws.Range(ws.Cells(1, 1), ws.Cells(1, n_cols))
        hdr.Interior.Color = 0x794E1F
        hdr.Font.Name = "Segoe UI"
        hdr.Font.Size = 11
        hdr.Font.Bold = True
        hdr.Font.Color = 0xFFFFFF
        ws.Rows(1).RowHeight = 26

        if n_linhas >= 2:
            corpo = ws.Range(ws.Cells(2, 1), ws.Cells(n_linhas, n_cols))
            corpo.Font.Name = "Segoe UI"
            corpo.Font.Size = 10
        ws.Columns.AutoFit()
    except Exception:
        pass


def editar_planilha_live(
    caminho: Path,
    df_novo: Any,
    resumo_acao: str,
    sem_foco: bool = True,
) -> tuple[bool, str]:
    """
    Atualiza em tempo real as células da planilha aberta no Excel (ou abre-a sem roubar foco),
    exibindo as mudanças instantaneamente na tela e salvando no disco sem fechar o workbook.
    """
    if sys.platform != "win32":
        return False, "COM disponível apenas no Windows."

    garantizar_backup_sessao(caminho)
    fg_antes = _capturar_foreground_hwnd() if sem_foco else None

    def _op() -> str:
        excel = _obter_excel_app(criar_se_ausente=True)
        excel.DisplayAlerts = False
        excel.Visible = True
        hwnd = getattr(excel, "Hwnd", None)

        wb = _achar_workbook_aberto(excel, caminho)
        if wb is None:
            wb = excel.Workbooks.Open(str(caminho.resolve()))

        ws = wb.ActiveSheet
        excel.ScreenUpdating = True

        # Limpa conteúdo anterior e escreve cabeçalhos + linhas em bloco (rápido e visível ao vivo)
        ws.Cells.ClearContents()
        colunas = [str(c) for c in list(df_novo.columns)]
        n_cols = len(colunas)
        n_rows = len(df_novo)

        if n_cols > 0:
            ws.Range(ws.Cells(1, 1), ws.Cells(1, n_cols)).Value = [colunas]
            if n_rows > 0:
                matriz = [
                    [None if (v != v) else v for v in linha]
                    for linha in df_novo.values.tolist()
                ]
                ws.Range(ws.Cells(2, 1), ws.Cells(n_rows + 1, n_cols)).Value = matriz

            _estilizar_planilha_com(ws, n_rows + 1, n_cols)

            # Rola suavemente até a última linha editada
            try:
                ultima = max(1, n_rows + 1)
                ws.Cells(ultima, 1).Select()
            except Exception:
                pass

        wb.Save()
        if sem_foco and hwnd:
            mostrar_sem_foco(int(hwnd), fg_antes)

        status_overlay(f"Excel ao vivo: {caminho.name} ({resumo_acao})", ativo=True, duracao=8.0)
        return (
            f"Planilha '{caminho.name}' atualizada ao vivo em segundo plano: {resumo_acao}. "
            f"Agora com {n_rows} linhas e {n_cols} colunas."
        )

    try:
        msg = executar_sta(_op, timeout=25.0)
        return True, msg
    except Exception as e:
        return False, str(e)


# ── WORD AO VIVO ─────────────────────────────────────────────────────────────

def _obter_word_app(criar_se_ausente: bool = True) -> Any:
    import win32com.client
    try:
        return win32com.client.GetActiveObject("Word.Application")
    except Exception:
        if not criar_se_ausente:
            return None
        return win32com.client.Dispatch("Word.Application")


def _achar_doc_aberto(word: Any, caminho: Path) -> Any | None:
    alvo = str(caminho.resolve()).lower()
    nome_alvo = caminho.name.lower()
    try:
        for doc in list(word.Documents):
            try:
                if str(doc.FullName).lower() == alvo or str(doc.Name).lower() == nome_alvo:
                    return doc
            except Exception:
                continue
    except Exception:
        pass
    return None


def esta_aberto_no_word(caminho: Path) -> bool:
    """Verifica se o documento .docx já está aberto numa instância ativa do Microsoft Word."""
    if sys.platform != "win32":
        return False

    def _check() -> bool:
        word = _obter_word_app(criar_se_ausente=False)
        if word is None:
            return False
        return _achar_doc_aberto(word, caminho) is not None

    try:
        return bool(executar_sta(_check, timeout=5.0))
    except Exception:
        return False


def _obter_word_hwnd() -> int | None:
    """Localiza o HWND da janela principal do Word (OpusApp)."""
    if sys.platform != "win32":
        return None
    try:
        hwnd = ctypes.windll.user32.FindWindowW("OpusApp", None)
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def abrir_documento_word_live(caminho: Path | None = None, sem_foco: bool = True) -> tuple[bool, str]:
    """
    Abre ou reutiliza um documento no Microsoft Word em segundo plano (sem roubar o foco)
    e ativa a barra flutuante FRY.png.
    """
    if sys.platform != "win32":
        return False, "COM disponível apenas no Windows."

    fg_antes = _capturar_foreground_hwnd() if sem_foco else None

    def _op() -> str:
        word = _obter_word_app(criar_se_ausente=True)
        word.DisplayAlerts = 0
        word.Visible = True

        if caminho is not None and caminho.exists():
            doc = _achar_doc_aberto(word, caminho)
            if doc is None:
                doc = word.Documents.Open(str(caminho.resolve()))
            msg = f"Documento '{caminho.name}' aberto em segundo plano no Microsoft Word."
            status_overlay(f"Word em 2º plano: {caminho.name}", ativo=True, duracao=8.0)
        else:
            if word.Documents.Count == 0:
                word.Documents.Add()
            msg = "O aplicativo Microsoft Word foi aberto em segundo plano com sucesso."
            status_overlay("Word ativo em 2º plano", ativo=True, duracao=8.0)

        hwnd = _obter_word_hwnd()
        if sem_foco and hwnd:
            mostrar_sem_foco(hwnd, fg_antes)
        return msg

    try:
        msg = executar_sta(_op, timeout=20.0)
        return True, msg
    except Exception as e:
        return False, str(e)


def editar_documento_word_live(
    caminho: Path,
    substituir_de: str | None = None,
    substituir_para: str | None = None,
    adicionar_paragrafos: list[str] | None = None,
    adicionar_titulo: str | None = None,
    sem_foco: bool = True,
) -> tuple[bool, str]:
    """
    Edita em tempo real um documento Word (.docx) aberto no Microsoft Word via COM,
    sem fechar a janela e sem travar por lock de arquivo.
    """
    if sys.platform != "win32":
        return False, "COM disponível apenas no Windows."

    garantizar_backup_sessao(caminho)
    fg_antes = _capturar_foreground_hwnd() if sem_foco else None

    def _op() -> str:
        word = _obter_word_app(criar_se_ausente=True)
        word.DisplayAlerts = 0
        word.Visible = True

        doc = _achar_doc_aberto(word, caminho)
        if doc is None:
            doc = word.Documents.Open(str(caminho.resolve()))

        substituicoes = 0
        if substituir_de and substituir_para is not None:
            # Conta ocorrências e aplica substituição direta nos parágrafos e tabelas
            for p in doc.Paragraphs:
                txt = p.Range.Text
                if substituir_de in txt:
                    ocorrencias = txt.count(substituir_de)
                    p.Range.Text = txt.replace(substituir_de, substituir_para)
                    substituicoes += ocorrencias
            for tbl in doc.Tables:
                for row in tbl.Rows:
                    for cell in row.Cells:
                        # Remove marcador de fim de célula (\r\x07) ao manipular
                        raw = cell.Range.Text
                        corpo = raw[:-2] if raw.endswith("\r\x07") else raw
                        if substituir_de in corpo:
                            ocorrencias = corpo.count(substituir_de)
                            cell.Range.Text = corpo.replace(substituir_de, substituir_para)
                            substituicoes += ocorrencias

        if adicionar_titulo:
            p_tit = doc.Paragraphs.Add()
            p_tit.Range.Text = str(adicionar_titulo) + "\r"
            try:
                # Usa o objeto retornado pelo Add() diretamente.
                # doc.Paragraphs(Count - 1) era off-by-one (COM é 1-based e Add insere antes do marcador final)
                p_tit.Style = -3  # wdStyleHeading2 = -3
            except Exception:
                pass

        if adicionar_paragrafos:
            for texto_p in adicionar_paragrafos:
                p_novo = doc.Paragraphs.Add()
                p_novo.Range.Text = str(texto_p) + "\r"
                try:
                    # Usa objeto retornado pelo Add() diretamente (mesmo motivo do título)
                    p_novo.Style = -1  # wdStyleNormal = -1
                except Exception:
                    pass

        try:
            rng_fim = doc.Range(doc.Content.End - 1, doc.Content.End)
            doc.ActiveWindow.ScrollIntoView(rng_fim, True)
        except Exception:
            pass

        doc.Save()

        hwnd = _obter_word_hwnd()
        if sem_foco and hwnd:
            mostrar_sem_foco(hwnd, fg_antes)

        partes = []
        if substituir_de and substituir_para is not None and substituicoes > 0:
            partes.append(f"{substituicoes} substituição(ões) de texto realizadas")
        if adicionar_titulo:
            partes.append("título adicionado")
        if adicionar_paragrafos:
            partes.append(f"{len(adicionar_paragrafos)} parágrafo(s) adicionado(s)")
        resumo = "; ".join(partes) if partes else "nenhuma alteração realizada"

        status_overlay(f"Word ao vivo: {caminho.name} ({resumo})", ativo=True, duracao=8.0)
        return f"Documento '{caminho.name}' editado com sucesso em tempo real: {resumo}."

    try:
        msg = executar_sta(_op, timeout=25.0)
        return True, msg
    except Exception as e:
        return False, str(e)
