"""
Reprodução local de áudio (MP3) nas caixas de som do PC para a F.R.Y.I.Vs.

Usa a API MCI nativa do Windows (winmm.dll via ctypes): sem dependências novas.
Todas as chamadas MCI rodam numa única thread dedicada (MCI é sensível à thread
que abriu o dispositivo) e os áudios são enfileirados para nunca se sobreporem.
"""

from __future__ import annotations

import ctypes
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import uuid

_fila: "queue.Queue[tuple[str, threading.Event]]" = queue.Queue()
_thread: threading.Thread | None = None
_lock = threading.Lock()
_tocando = threading.Event()
_parar = threading.Event()
_ultimo_fim: float = 0.0
_TMP_DIR = os.path.join(tempfile.gettempdir(), "fryivs_audio")


def _mci(comando: str) -> str:
    buf = ctypes.create_unicode_buffer(256)
    erro = ctypes.windll.winmm.mciSendStringW(comando, buf, 255, 0)
    if erro:
        raise OSError(f"MCI erro {erro} em '{comando}'")
    return buf.value


def _tocar_arquivo(caminho: str) -> None:
    alias = f"fry{uuid.uuid4().hex[:8]}"
    mci_type = "waveaudio" if caminho.lower().endswith(".wav") else "mpegvideo"
    _mci(f'open "{caminho}" type {mci_type} alias {alias}')
    try:
        _mci(f"play {alias}")
        inicio = time.time()
        while not _parar.is_set():
            modo = _mci(f"status {alias} mode")
            if modo != "playing" and time.time() - inicio > 0.3:
                break
            if time.time() - inicio > 120:
                break
            time.sleep(0.05)
    finally:
        try:
            _mci(f"close {alias}")
        except OSError:
            pass


def _worker() -> None:
    global _ultimo_fim
    while True:
        caminho, feito = _fila.get()
        _parar.clear()
        _tocando.set()
        try:
            _tocar_arquivo(caminho)
        except Exception as e:
            print(f"[AudioPlayer] Falha ao tocar '{caminho}': {e}")
        finally:
            _ultimo_fim = time.time()
            if _fila.empty():
                _tocando.clear()
            feito.set()
            try:
                if os.path.dirname(caminho) == _TMP_DIR:
                    os.remove(caminho)
            except OSError:
                pass


def _garantir_thread() -> None:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_worker, name="FryivsAudioPlayer", daemon=True)
            _thread.start()


def disponivel() -> bool:
    return sys.platform == "win32"


def tocar(caminho: str, bloquear: bool = True, timeout: float = 120.0) -> bool:
    """
    Toca um MP3 nas caixas de som. O arquivo é copiado para uma pasta temporária
    para não travar o original (ex.: resposta.mp3 é sobrescrito a cada resposta).
    Silêncio total quando o sistema estiver mutado.
    """
    if not disponivel() or not caminho or not os.path.exists(caminho):
        return False
    try:
        from core.mute_state import is_muted
        if is_muted():
            print("[AudioPlayer] Reprodução bloqueada (sistema mutado).")
            return False
    except Exception:
        pass
    os.makedirs(_TMP_DIR, exist_ok=True)
    ext = ".wav" if caminho.lower().endswith(".wav") else ".mp3"
    copia = os.path.join(_TMP_DIR, f"{uuid.uuid4().hex}{ext}")
    try:
        shutil.copy2(caminho, copia)
    except OSError:
        copia = caminho
    _garantir_thread()
    feito = threading.Event()
    _tocando.set()
    _fila.put((copia, feito))
    if bloquear:
        feito.wait(timeout)
    return True


def parar() -> None:
    """Interrompe o áudio atual e descarta os pendentes."""
    while not _fila.empty():
        try:
            _, ev = _fila.get_nowait()
            ev.set()
        except queue.Empty:
            break
    _parar.set()


def tocando(margem: float = 0.35) -> bool:
    """True enquanto toca (e por `margem` segundos após o fim, para o eco da sala)."""
    return _tocando.is_set() or (time.time() - _ultimo_fim) < margem

