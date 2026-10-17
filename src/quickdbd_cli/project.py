"""Input discovery and the compile pipeline shared by every command."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import layout
from .measure import model_json
from .model import Schema
from .parser import compile_sources


def discover(inputs: list[Path]) -> list[Path]:
    """Expand directories to every ``*.txt`` beneath them (recursive, sorted)."""
    files: list[Path] = []
    for p in inputs:
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*.txt") if f.is_file()))
        elif p.exists():
            files.append(p)
        else:
            raise FileNotFoundError(f"no such file or directory: {p}")
    seen: set[Path] = set()
    out = []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            out.append(f)
    return out


def display_path(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


@dataclass
class Project:
    inputs: list[Path]
    files: list[Path]
    sidecar: Path

    @classmethod
    def open(cls, inputs: list[Path], sidecar: Path | None = None) -> Project:
        files = discover(inputs)
        if not files:
            raise FileNotFoundError("no .txt schema files found in: " + ", ".join(map(str, inputs)))
        return cls(inputs, files, sidecar or layout.default_sidecar(files, inputs))

    def sources(self) -> list[tuple[str, str]]:
        return [(display_path(f), f.read_text(encoding="utf-8")) for f in self.files]

    def compile(self) -> Schema:
        return compile_sources(self.sources())

    def build(self, schema: Schema, reset: bool = False, select: str | None = None) -> tuple[dict, dict]:
        """Returns (model, positions) with positions keyed by table id as [x, y].

        ``select`` is a dbt-style selector expression (see ``select_model``); unselected tables are dropped.
        """
        model = model_json(schema)
        if select:
            model = select_model(model, select)
        side = {} if reset else layout.read_sidecar(self.sidecar)
        pos = layout.resolve_positions(model, side, schema.layout, reset=reset)
        return model, {k: [v[0], v[1]] for k, v in pos.items()}

    def save_positions(self, model: dict, positions: dict) -> None:
        by_name = {t["name"]: tuple(positions[t["id"]]) for t in model["tables"] if t["id"] in positions}
        layout.write_sidecar(self.sidecar, by_name)


class SelectionError(ValueError):
    pass


def selector_expr(select: list[str] | None, exclude: list[str] | None) -> str:
    """Combine CLI --select / --exclude values into one selector expression."""
    parts = [x for v in (select or []) for x in v.split()]
    parts += ["!" + x for v in (exclude or []) for x in v.split()]
    return " ".join(parts)


def select_model(model: dict, expr: str) -> dict:
    """Keep only the tables matched by a dbt-style selector (and relationships among them)."""
    from .jsrt import runtime

    rt = runtime()
    rt.load("render.js")
    try:
        ids = rt.call("qdbdSelect", model, expr)
    except Exception as e:  # JS exceptions from mini-racer: "<anonymous>:N: Error: message"
        msg = str(e).splitlines()[0]
        raise SelectionError(re.sub(r"^.*?Error: ", "", msg)) from None
    if ids is None:
        return model
    if not ids:
        raise SelectionError(f"no tables match '{expr}'")
    keep = set(ids)
    return {
        **model,
        "tables": [t for t in model["tables"] if t["id"] in keep],
        "rels": [r for r in model["rels"] if r["a"]["t"] in keep and r["b"]["t"] in keep],
    }
