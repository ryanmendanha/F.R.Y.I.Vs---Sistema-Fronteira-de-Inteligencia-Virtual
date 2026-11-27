"""
Sincroniza os ícones oficiais do Icons8 definidos em icons8.json
para ui/static/icons8/ e gera folha de contato visual para auditoria.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "icons8.json"
OUT_STATIC = ROOT / "ui" / "static" / "icons8"
OUT_PUBLIC = ROOT / "ui" / "react-app" / "public" / "static" / "icons8"


def sync_all(sheet_output: Path | None = None) -> int:
    cfg = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    items: dict[str, dict[str, str]] = cfg["icons"]["items"]
    OUT_STATIC.mkdir(parents=True, exist_ok=True)
    OUT_PUBLIC.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(timeout=20.0, follow_redirects=True)

    def _download(kv: tuple[str, dict[str, str]]) -> tuple[str, int]:
        name, meta = kv
        icon_id = meta["id"]
        r = client.get(
            "https://img.icons8.com/",
            params={"id": icon_id, "format": "png", "size": "96", "color": "ffffff"},
        )
        if r.status_code != 200 or len(r.content) < 120:
            raise RuntimeError(f"Falha ao baixar {name} ({icon_id}): HTTP {r.status_code}")
        (OUT_STATIC / f"{name}.png").write_bytes(r.content)
        (OUT_PUBLIC / f"{name}.png").write_bytes(r.content)
        return name, len(r.content)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_download, items.items()))

    if sheet_output is not None:
        from PIL import Image, ImageDraw

        cols, cell_w, cell_h = 10, 114, 92
        names = sorted(items.keys())
        rows = (len(names) + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (7, 14, 28, 255))
        draw = ImageDraw.Draw(sheet)
        for idx, name in enumerate(names):
            row, col = divmod(idx, cols)
            x0, y0 = col * cell_w, row * cell_h
            im = Image.open(OUT_STATIC / f"{name}.png").convert("RGBA").resize((44, 44), Image.LANCZOS)
            sheet.paste(im, (x0 + (cell_w - 44) // 2, y0 + 12), im)
            draw.text((x0 + 6, y0 + 66), name[:16], fill=(125, 211, 252, 255))
        sheet_output.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(sheet_output)

    print(f"[Icons8] {len(results)} ícones sincronizados em {OUT_STATIC}")
    return len(results)


if __name__ == "__main__":
    import sys

    sheet = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sync_all(sheet)

