"""Text measurement and the diagram model handed to render.js.

Widths come from a committed per-glyph table for the bundled Inter font
(see scripts/gen_font_metrics.py), so Python, the browser, and the PNG export agree.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import PurePosixPath

from . import tags
from .model import Column, Schema, Table

STYLE = {
    "font": "Inter",
    "headerH": 32,
    "headerSize": 14,
    "rowH": 24,
    "rowSize": 12,
    "padX": 12,
    "gap": 20,
    "keyW": 19,
    "badgeSize": 9,
    "badgePad": 4,
    "badgeGap": 4,
    "bottomPad": 4,
    "minW": 120,
}


@cache
def _metrics() -> dict:
    return json.loads(resources.files("quickdbd_cli").joinpath("assets/font-metrics.json").read_text())


def text_width(text: str, size: float, bold: bool = False) -> float:
    table = _metrics()["bold" if bold else "regular"]
    return round(sum(table.get(ch, 0.6) for ch in text) * size, 2)


def badges(col: Column) -> list[str]:
    out = []
    if col.identity:
        out.append("auto")
    if col.unique:
        out.append("unique")
    if col.index:
        out.append("index")
    if col.nullable:
        out.append("null")
    if col.default is not None:
        out.append(f"={col.default}")
    return out


def _column_json(col: Column) -> dict:
    s = STYLE
    bold = col.pk or col.fk
    name_w = text_width(col.name, s["rowSize"], bold)
    bs = [{"t": b, "w": round(text_width(b, s["badgeSize"]) + 2 * s["badgePad"], 2)} for b in badges(col)]
    type_w = text_width(col.type or "", s["rowSize"])
    out = {
        "id": col.id,
        "name": col.name,
        "type": col.type or "",
        "pk": col.pk,
        "fk": col.fk,
        "nullable": col.nullable,
        "unique": col.unique,
        "index": col.index,
        "identity": col.identity,
        "default": col.default,
        "nameW": name_w,
        "typeW": type_w,
        "badges": bs,
    }
    if col.comments:
        out["doc"] = "\n".join(col.comments)
    return out


def table_json(table: Table) -> dict:
    s = STYLE
    cols = [_column_json(c) for c in table.columns.values() if not c.virtual]
    name_w = text_width(table.name, s["headerSize"])
    w = name_w + 2 * s["padX"]
    for c in cols:
        row = c["nameW"] + c["typeW"] + 2 * s["padX"] + s["gap"]
        row += sum(b["w"] + s["badgeGap"] for b in c["badges"])
        if c["pk"]:
            row += s["keyW"]
        w = max(w, row)
    w = max(round(w), s["minW"])
    h = s["headerH"] + len(cols) * s["rowH"] + s["bottomPad"]
    out = {"id": table.id, "name": table.name, "aliases": table.aliases, "w": w, "h": h, "nameW": name_w, "cols": cols}
    if table.comments:
        out["doc"] = "\n".join(table.comments)
    return out


def _groups(schema: Schema) -> dict[str, str]:
    """Explorer group per source file: the path without the common folder and ``.txt``; "" for one file."""
    paths = sorted({t.path for t in schema.tables.values()})
    if len(paths) <= 1:
        return {p: "" for p in paths}
    parts = [PurePosixPath(p.replace("\\", "/")).parts for p in paths]
    common = 0
    while all(len(x) > common + 1 for x in parts) and len({x[common] for x in parts}) == 1:
        common += 1
    out = {}
    for p, x in zip(paths, parts, strict=True):
        rel = "/".join(x[common:])
        out[p] = rel[:-4] if rel.endswith(".txt") else rel
    return out


def model_json(schema: Schema) -> dict:
    """Plain-JSON diagram model (no positions)."""
    groups = _groups(schema)
    rels = []
    for r in schema.valid_relationships():
        rels.append(
            {
                "a": {"t": r.a.table, "c": r.a.column, "card": r.a.card},
                "b": {"t": r.b.table, "c": r.b.column, "card": r.b.card},
            }
        )
    tables = [
        {**table_json(t), "group": groups[t.path], "file": t.path, "line": t.line} for t in schema.tables.values()
    ]
    legend = tags.annotate(schema, tables)
    out = {
        "style": STYLE,
        "tables": tables,
        "rels": rels,
        "zoom": schema.zoom,
        "position": list(schema.position) if schema.position else None,
    }
    if legend:
        out["tags"] = legend
    return out
