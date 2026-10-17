"""Regenerate src/quickdbd_cli/assets/font-metrics.json from the bundled Inter TTFs.

Dev-only: needs fontTools (`pip install fonttools`).
"""

import json
from pathlib import Path

from fontTools.ttLib import TTFont

ASSETS = Path(__file__).resolve().parent.parent / "src" / "quickdbd_cli" / "assets"
RANGES = [(0x20, 0x7F), (0xA0, 0x180)]


def widths(path: Path) -> dict:
    font = TTFont(path)
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    out = {}
    for lo, hi in RANGES:
        for cp in range(lo, hi):
            glyph = cmap.get(cp)
            if glyph:
                out[chr(cp)] = round(hmtx[glyph][0] / upm, 4)
    return out


def main() -> None:
    data = {
        "regular": widths(ASSETS / "Inter-Regular.ttf"),
        "bold": widths(ASSETS / "Inter-Bold.ttf"),
    }
    (ASSETS / "font-metrics.json").write_text(json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
