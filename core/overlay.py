"""
Controlador do HUD 3D flutuante do Modo Copiloto da F.R.Y.I.Vs.
O servidor e as skills de navegador/sistema atualizam `data/overlay_state.json`
e o processo `ui/overlay_bar.py` exibe o HUD 3D exclusivamente sobre o Chrome,
Edge ou aplicativos externos (nunca sobre a interface principal da IA).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
STATE_FILE = RAIZ / "data" / "overlay_state.json"
_proc: subprocess.Popen | None = None


def _em_teste() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _matar_overlays_antigos() -> None:
    """Encerra qualquer processo órfão anterior de ui/overlay_bar.py."""
    global _proc
    meu_pid = _proc.pid if (_proc is not None and _proc.poll() is None) else None
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if meu_pid and p.info.get("pid") == meu_pid:
                    continue
                cmd = " ".join(p.info.get("cmdline") or [])
                if "overlay_bar.py" in cmd:
                    p.kill()
            except Exception:
                pass
    except Exception:
        pass


def iniciar_overlay() -> None:
    """Garante que o processo do HUD 3D externo (`ui/overlay_bar.py`) esteja em execução."""
    global _proc
    if _em_teste() or sys.platform != "win32":
        return
    if _proc is not None and _proc.poll() is None:
        return
    _matar_overlays_antigos()
    script = RAIZ / "ui" / "overlay_bar.py"
    if not script.exists():
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    try:
        _proc = subprocess.Popen(
            [exe, str(script)],
            cwd=str(RAIZ),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        _proc = None


def parar_overlay() -> None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
    _proc = None
    _matar_overlays_antigos()
    status_overlay("", ativo=False, duracao=0.0)


def status_overlay(texto: str, ativo: bool = True, duracao: float = 8.0) -> None:
    """Atualiza o estado do HUD 3D externo (`data/overlay_state.json`)."""
    try:
        if ativo and not _em_teste():
            iniciar_overlay()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "active": ativo,
                    "status": texto,
                    "expires": time.time() + duracao,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass
