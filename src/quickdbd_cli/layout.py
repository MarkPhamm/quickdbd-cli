"""Table positions: sidecar file, QuickDBD [layout] import, ELK auto-layout, new-table placement."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .jsrt import runtime

_GLUE = """
function qdbdElkLayout(graph) {
  return new ELK().layout(graph).then(function (r) {
    var out = {};
    (r.children || []).forEach(function (c) { out[c.id] = [Math.round(c.x), Math.round(c.y)]; });
    return out;
  });
}
"""

# Stress layout keeps related tables close together (short relationship lines), then
# ELK's overlap removal pushes tables apart. Layered layouts were tried and produced very
# long lines on 200-table schemas.
STRESS_OPTIONS = {
    "elk.algorithm": "stress",
    "elk.stress.desiredEdgeLength": "250",
    "elk.randomSeed": "1",
}
OVERLAP_OPTIONS = {
    "elk.algorithm": "sporeOverlap",
    "elk.spacing.nodeNode": "40",
    "elk.randomSeed": "1",
}

MARGIN = 30
Positions = dict[str, tuple[int, int]]


def elk_layout(tables: list[dict], rels: list[dict]) -> Positions:
    """Lay out ``tables`` (model_json table dicts) with ELK; only rels between them are used."""
    if not tables:
        return {}
    ids = {t["id"] for t in tables}
    rt = runtime()
    rt.load("elk.bundled.js")
    if "glue" not in rt.loaded:
        rt.ctx.eval(_GLUE)
        rt.loaded.add("glue")
    edges = []
    seen = set()
    for r in rels:
        a, b = r["a"]["t"], r["b"]["t"]
        # Edges point from the referencing (many/FK) side to the referenced side.
        src, dst = (a, b) if r["a"]["card"] in ("many", "zeroMany") or r["b"]["card"] == "one" else (b, a)
        if src in ids and dst in ids and src != dst and (src, dst) not in seen:
            seen.add((src, dst))
            edges.append({"id": f"e{len(edges)}", "sources": [src], "targets": [dst]})
    graph = {
        "id": "root",
        "layoutOptions": STRESS_OPTIONS,
        "children": [{"id": t["id"], "width": t["w"], "height": t["h"]} for t in tables],
        "edges": edges,
    }
    first = rt.call_async("qdbdElkLayout", graph)
    first = _landscape(tables, {k: (v[0], v[1]) for k, v in first.items()})
    graph = {
        "id": "root",
        "layoutOptions": OVERLAP_OPTIONS,
        "children": [
            {"id": t["id"], "width": t["w"], "height": t["h"], "x": first[t["id"]][0], "y": first[t["id"]][1]}
            for t in tables
        ],
        "edges": [],
    }
    raw = rt.call_async("qdbdElkLayout", graph)
    min_x = min(v[0] for v in raw.values())
    min_y = min(v[1] for v in raw.values())
    return {k: (int(v[0] - min_x), int(v[1] - min_y)) for k, v in raw.items()}


def _bbox(tables: list[dict], pos: dict) -> tuple[float, float]:
    xs = [pos[t["id"]][0] for t in tables] + [pos[t["id"]][0] + t["w"] for t in tables]
    ys = [pos[t["id"]][1] for t in tables] + [pos[t["id"]][1] + t["h"] for t in tables]
    return max(xs) - min(xs), max(ys) - min(ys)


def _landscape(tables: list[dict], pos: dict) -> dict:
    """Stress layout picks an arbitrary orientation; turn tall results 90 degrees so they fit screens."""
    w, h = _bbox(tables, pos)
    if h <= w * 1.15:
        return pos
    out = {}
    for t in tables:
        cx, cy = pos[t["id"]][0] + t["w"] / 2, pos[t["id"]][1] + t["h"] / 2
        nx, ny = cy, -cx  # rotate centres; table boxes stay upright
        out[t["id"]] = (nx - t["w"] / 2, ny - t["h"] / 2)
    return out


def _overlaps(x: float, y: float, w: float, h: float, rects: list[tuple[float, float, float, float]]) -> bool:
    for rx, ry, rw, rh in rects:
        if x < rx + rw + MARGIN and rx < x + w + MARGIN and y < ry + rh + MARGIN and ry < y + h + MARGIN:
            return True
    return False


def _free_spot(cx: float, cy: float, w: float, h: float, rects, step: int = 30) -> tuple[int, int]:
    """Nearest non-overlapping top-left position to centre (cx, cy), searched in square rings."""
    x0, y0 = cx - w / 2, cy - h / 2
    for ring in range(0, 400):
        cands = []
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) == ring:
                    cands.append((dx * dx + dy * dy, dx, dy))
        for _, dx, dy in sorted(cands):
            x, y = x0 + dx * step, y0 + dy * step
            if not _overlaps(x, y, w, h, rects):
                return int(round(x)), int(round(y))
    return int(round(x0)), int(round(y0))


def place_missing(tables: list[dict], rels: list[dict], positions: Positions) -> Positions:
    """Positions for every table. Existing positions never move.

    Tables with already-placed neighbours go into the nearest free space around those neighbours;
    the rest are laid out together with ELK and put below the existing diagram.
    """
    by_id = {t["id"]: t for t in tables}
    pos: Positions = {k: v for k, v in positions.items() if k in by_id}
    missing = [t["id"] for t in tables if t["id"] not in pos]
    if not missing:
        return pos
    if not pos:
        return elk_layout(tables, rels)

    neighbours: dict[str, list[str]] = {t["id"]: [] for t in tables}
    for r in rels:
        a, b = r["a"]["t"], r["b"]["t"]
        if a != b and a in neighbours and b in neighbours:
            neighbours[a].append(b)
            neighbours[b].append(a)
    order = {tid: i for i, tid in enumerate(t["id"] for t in tables)}
    rects = [(x, y, by_id[k]["w"], by_id[k]["h"]) for k, (x, y) in pos.items()]

    pending = set(missing)
    while True:
        ready = [(sum(1 for n in neighbours[t] if n in pos), t) for t in pending]
        ready = [(n, t) for n, t in ready if n > 0]
        if not ready:
            break
        ready.sort(key=lambda nt: (-nt[0], order[nt[1]]))
        tid = ready[0][1]
        t = by_id[tid]
        placed = [n for n in neighbours[tid] if n in pos]
        cx = sum(pos[n][0] + by_id[n]["w"] / 2 for n in placed) / len(placed)
        cy = sum(pos[n][1] + by_id[n]["h"] / 2 for n in placed) / len(placed)
        x, y = _free_spot(cx, cy, t["w"], t["h"], rects)
        pos[tid] = (x, y)
        rects.append((x, y, t["w"], t["h"]))
        pending.discard(tid)

    if pending:
        rest = [by_id[t] for t in missing if t in pending]
        block = elk_layout(rest, rels)
        min_x = min(r[0] for r in rects)
        max_y = max(r[1] + r[3] for r in rects)
        bx = min(v[0] for v in block.values())
        by = min(v[1] for v in block.values())
        for tid, (x, y) in block.items():
            pos[tid] = (x - bx + min_x, y - by + max_y + 120)
    return pos


# --------------------------------------------------------------------------- sidecar


def default_sidecar(files: list[Path], inputs: list[Path]) -> Path:
    if len(inputs) == 1 and inputs[0].is_file():
        f = inputs[0]
        return f.with_name(f.stem + ".layout.json")
    if len(inputs) == 1 and inputs[0].is_dir():
        return inputs[0] / "qdbd.layout.json"
    common = Path(os.path.commonpath([str(p.resolve().parent) for p in files])) if files else Path.cwd()
    return common / "qdbd.layout.json"


def read_sidecar(path: Path) -> dict[str, tuple[int, int]]:
    """Returns {table name: (x, y)}."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: (int(v["x"]), int(v["y"])) for name, v in data.get("tables", {}).items()}


def write_sidecar(path: Path, by_name: dict[str, tuple[int, int]]) -> None:
    data = {
        "version": 1,
        "tables": {n: {"x": int(x), "y": int(y)} for n, (x, y) in sorted(by_name.items())},
    }
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".qdbd-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def resolve_positions(
    model: dict, sidecar: dict[str, tuple[int, int]], qdbd_layout: dict, reset: bool = False
) -> Positions:
    """Sidecar (by table name) > QuickDBD [layout] section > auto placement."""
    tables = model["tables"]
    pos: Positions = {}
    if not reset:
        for t in tables:
            if t["name"] in sidecar:
                pos[t["id"]] = sidecar[t["name"]]
            elif t["id"] in qdbd_layout:
                x, y = qdbd_layout[t["id"]]
                pos[t["id"]] = (int(x), int(y))
    return place_missing(tables, model["rels"], pos)


def positions_by_name(model: dict, pos: Positions) -> dict[str, tuple[int, int]]:
    return {t["name"]: pos[t["id"]] for t in model["tables"] if t["id"] in pos}
