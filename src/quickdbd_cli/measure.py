"""Text measurement and the diagram model handed to render.js.

Widths come from a committed per-glyph table for the bundled Inter font
(see scripts/gen_font_metrics.py), so Python, the browser, and the PNG export agree.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import PurePath, PurePosixPath

from . import tags
from .model import VIRTUAL_FIELD, Column, End, Relationship, Schema, Table

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
    return json.loads(resources.files("quickdbd_cli").joinpath("assets/font-metrics.json").read_text(encoding="utf-8"))


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
    """Explorer group per source file: the path without the common folder and ``.txt``/``.dbml``; "" for one file."""
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
        out[p] = rel.rsplit(".", 1)[0] if rel.endswith((".txt", ".dbml")) else rel
    return out


def _child_parent(r: Relationship) -> tuple[End, End]:
    many = ("many", "zeroMany")
    return (r.a, r.b) if r.a.card in many or r.b.card not in many else (r.b, r.a)


def composite_keys(schema: Schema, rels: list[Relationship]) -> dict[int, int]:
    """Index in ``rels`` -> composite key number, for relationships that only together make one join: the column
    pairs of one multi-column DBML ref, or FK lines from one table that cover exactly another table's composite PK."""
    groups: dict[tuple, list[int]] = {}
    for i, r in enumerate(rels):
        if VIRTUAL_FIELD in (r.a.column, r.b.column):
            continue
        child, parent = _child_parent(r)
        groups.setdefault(("ref", r.path, r.line, child.table, parent.table), []).append(i)
        groups.setdefault(("pk", child.table, parent.table), []).append(i)
    out: dict[int, int] = {}
    for key, idx in groups.items():
        if len(idx) < 2 or any(i in out for i in idx):
            continue
        if key[0] == "pk":
            parent = schema.tables[key[2]]
            pk = {c.id for c in parent.columns.values() if c.pk}
            cols = [_child_parent(rels[i])[1].column for i in idx]
            if len(pk) < 2 or len(set(cols)) != len(cols) or set(cols) != pk:
                continue
        n = len(set(out.values()))
        for i in idx:
            out[i] = n
    return out


def model_json(schema: Schema) -> dict:
    """Plain-JSON diagram model (no positions)."""
    groups = _groups(schema)
    valid = schema.valid_relationships()
    keys = composite_keys(schema, valid)
    rels = []
    for i, r in enumerate(valid):
        rel = {
            "a": {"t": r.a.table, "c": r.a.column, "card": r.a.card},
            "b": {"t": r.b.table, "c": r.b.column, "card": r.b.card},
        }
        if i in keys:
            rel["k"] = keys[i]
        rels.append(rel)
    tables = [
        {**table_json(t), "group": t.group or groups[t.path], "file": PurePath(t.path).as_posix(), "line": t.line}
        for t in schema.tables.values()
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
