"""Input discovery and the compile pipeline shared by every command."""

from __future__ import annotations

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

    def build(self, schema: Schema, reset: bool = False) -> tuple[dict, dict]:
        """Returns (model, positions) with positions keyed by table id as [x, y]."""
        model = model_json(schema)
        side = {} if reset else layout.read_sidecar(self.sidecar)
        pos = layout.resolve_positions(model, side, schema.layout, reset=reset)
        return model, {k: [v[0], v[1]] for k, v in pos.items()}

    def save_positions(self, model: dict, positions: dict) -> None:
        by_name = {t["name"]: tuple(positions[t["id"]]) for t in model["tables"] if t["id"] in positions}
        layout.write_sidecar(self.sidecar, by_name)
