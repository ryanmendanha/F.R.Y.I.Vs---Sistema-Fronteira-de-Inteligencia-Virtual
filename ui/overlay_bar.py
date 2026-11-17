"""
HUD 3D Flutuante do Modo Copiloto (FRY • IVS — Modo Copiloto).

Exibe os quadros renderizados em WebGL 3D de `FRY • IVS — Modo Copiloto (1).html`
no topo-centro da tela SOMENTE quando:
- Há uma pesquisa no Chrome/Edge ou uma ação externa ativa em `data/overlay_state.json`; E
- O usuário NÃO está na janela/aba da interface principal da IA (`F.R.Y.I.Vs - Neural Interface`).

É 100% click-through (`WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`), não roubando foco nem
bloqueando cliques durante a navegação no Chrome ou Edge.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
import tkinter as tk
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
STATE_FILE = RAIZ / "data" / "overlay_state.json"
FRAMES_DIR = RAIZ / "ui" / "assets" / "copiloto_3d_frames"
AI_UI_TITLES = (
    "f.r.y.i.vs - neural interface",
    "127.0.0.1:8000",
    "localhost:8000",
)

TRANSP = "#ff00fe"
BORDA_CIANO = "#22e6ff"
FUNDO_STATUS = "#050b24"

W, H = 780, 102
BAR_H = 73


def _foreground_title() -> str:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def _ler_estado() -> dict:
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if d.get("active") and time.time() > float(d.get("expires", 0)):
            d["active"] = False
        return d
    except Exception:
        return {"active": False}


def _esta_na_interface_ia(titulo_janela: str) -> bool:
    t = (titulo_janela or "").lower()
    return any(marcador in t for marcador in AI_UI_TITLES)


class OverlayBar:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSP)
        try:
            self.root.attributes("-transparentcolor", TRANSP)
        except tk.TclError:
            pass

        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{W}x{H}+{(sw - W) // 2}+6")

        c = tk.Canvas(self.root, width=W, height=H, bg=TRANSP, highlightthickness=0)
        c.pack()

        cx = W // 2
        self._frames = self._carregar_frames_3d()
        self._frame_idx = 0

        if self._frames:
            self._hud_img_id = c.create_image(cx, BAR_H // 2 + 2, image=self._frames[0])
        else:
            self._hud_img_id = None

        # Pílula inferior de telemetria/status em tempo real sobre o Chrome/Edge
        self.status_id = c.create_text(
            cx,
            H - 12,
            text="",
            fill="#c9f8ff",
            font=("Consolas", 9, "bold"),
        )
        self.status_bg = c.create_rectangle(
            0, 0, 0, 0, fill=FUNDO_STATUS, outline=BORDA_CIANO, width=1
        )
        c.tag_lower(self.status_bg, self.status_id)

        self.canvas = c
        self._visivel = True

        self.root.update_idletasks()
        self._tornar_click_through()
        self._esconder()
        self._tick()

    def _carregar_frames_3d(self) -> list:
        frames = []
        try:
            from PIL import Image, ImageTk

            arquivos = sorted(FRAMES_DIR.glob("frame_*.png"))
            for arq in arquivos:
                img = Image.open(arq).convert("RGB")
                frames.append(ImageTk.PhotoImage(img))
        except Exception:
            pass
        return frames

    def _tornar_click_through(self) -> None:
        if sys.platform != "win32":
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
            WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                st | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
        except Exception:
            pass

    def _mostrar(self) -> None:
        if not self._visivel:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self._tornar_click_through()
            self._visivel = True

    def _esconder(self) -> None:
        if self._visivel:
            self.root.withdraw()
            self._visivel = False

    def _tick(self) -> None:
        est = _ler_estado()
        fg = _foreground_title()
        na_interface_ia = _esta_na_interface_ia(fg)

        if est.get("active") and not na_interface_ia:
            c = self.canvas
            if self._frames and self._hud_img_id is not None:
                self._frame_idx = (self._frame_idx + 1) % len(self._frames)
                c.itemconfigure(self._hud_img_id, image=self._frames[self._frame_idx])

            texto = str(est.get("status", "")).strip()[:74]
            c.itemconfigure(self.status_id, text=texto)
            if texto:
                x1, y1, x2, y2 = c.bbox(self.status_id)
                c.coords(self.status_bg, x1 - 12, y1 - 2, x2 + 12, y2 + 2)
            else:
                c.coords(self.status_bg, 0, 0, 0, 0)

            self._mostrar()
        else:
            self._esconder()

        self.root.after(90, self._tick)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    OverlayBar().run()
