"""Static SVG / PNG export via render.js (in V8) and resvg."""

from __future__ import annotations

import base64
from functools import cache
from importlib import resources

from . import layout
from .jsrt import runtime


def _asset_bytes(name: str) -> bytes:
    return resources.files("quickdbd_cli").joinpath(f"assets/{name}").read_bytes()


@cache
def font_css() -> str:
    out = []
    for weight, name in (("normal", "Inter-Regular.woff2"), ("bold", "Inter-Bold.woff2")):
        b64 = base64.b64encode(_asset_bytes(name)).decode("ascii")
        out.append(
            f"@font-face{{font-family:Inter;font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "".join(out)


def find_table(model: dict, name: str) -> dict | None:
    for key in ("name", "id"):
        for t in model["tables"]:
            if t[key] == name:
                return t
    low = name.lower()
    for t in model["tables"]:
        if t["name"].lower() == low or low in (a.lower() for a in t["aliases"]):
            return t
    return None


def focus_ids(model: dict, table_id: str, depth: int) -> list[str]:
    rt = runtime()
    rt.load("render.js")
    return rt.call("qdbdNeighbourhood", model, table_id, depth)


def render_svg(
    model: dict,
    positions: dict,
    only: list[str] | None = None,
    mode: str = "full",
    embed_font: bool = True,
    regions: bool = False,
) -> str:
    rt = runtime()
    rt.load("render.js")
    opts = {"mode": mode, "only": only, "regions": regions}
    if embed_font:
        opts["fontCss"] = font_css()
    return rt.call("qdbdRenderSvg", model, positions, opts)


def render_drawio(
    model: dict,
    positions: dict,
    only: list[str] | None = None,
    mode: str = "full",
    title: str = "ERD",
    regions: bool = False,
) -> str:
    """draw.io / diagrams.net file (mxGraph XML) with editable ER tables."""
    rt = runtime()
    rt.load("render.js")
    return rt.call(
        "qdbdRenderDrawio", model, positions, {"mode": mode, "only": only, "title": title, "regions": regions}
    )


def focus_positions(model: dict, positions: dict, ids: list[str]) -> dict:
    """Fresh compact ELK layout for a focus subset, so the image isn't mostly empty space."""
    keep = set(ids)
    tables = [t for t in model["tables"] if t["id"] in keep]
    rels = [r for r in model["rels"] if r["a"]["t"] in keep and r["b"]["t"] in keep]
    pos = layout.elk_layout(tables, rels)
    return {k: [v[0], v[1]] for k, v in pos.items()}


def svg_to_png(svg: str, scale: float = 2.0) -> bytes:
    import resvg_py

    fonts_dir = resources.files("quickdbd_cli").joinpath("assets")
    font_files = [str(fonts_dir.joinpath(n)) for n in ("Inter-Regular.ttf", "Inter-Bold.ttf")]
    data = resvg_py.svg_to_bytes(
        svg_string=svg,
        font_files=font_files,
        skip_system_fonts=True,
        sans_serif_family="Inter",
        zoom=scale,
    )
    return bytes(data)
