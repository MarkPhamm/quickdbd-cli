"""Which schema files belong together, found by walking a folder: `qdbd mcp` serves every project it finds.

A port of the VS Code extension's rules (vscode/src/target.ts and schema.ts, the sidebar's scan in sidebar.ts):
keep the two in step. tests/fixtures/targets/cases.json runs against both.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePath

from .dbt import HEADER
from .parser import syntax_of

SKIP = ("node_modules", "venv", "dbt_packages", "target", "site", "dist", "build")  # plus every dot-folder
MAX_FILES = 5000  # schema-file candidates, like the sidebar's findFiles cap
MAX_BYTES = 2_000_000
MAX_SCAN = 500  # an all-schema folder holds at most this many files
MAX_LINES = 5000
SCHEMA_EXT = (".txt", ".dbml")

_SEPARATOR = re.compile(r"^-+\s*$")
_KEYED = re.compile(r"(^|\s)(PK|FK)(\s|$)|^\s*rel\s", re.IGNORECASE)


def _lines(text: str) -> list[str]:
    return re.split(r"\r?\n", text, maxsplit=MAX_LINES)[:MAX_LINES]


def has_table(text: str) -> bool:
    """A header line followed by a `---` separator, i.e. at least one table."""
    lines = _lines(text)
    for i in range(1, len(lines)):
        prev = lines[i - 1].strip()
        if _SEPARATOR.match(lines[i]) and prev and not prev.startswith("#"):
            return True
    return False


def looks_like_quickdbd(text: str) -> bool:
    """Strict enough to switch a plain .txt to QuickDBD: a table plus a PK/FK/rel line."""
    if not has_table(text):
        return False
    return any(not ln.lstrip().startswith("#") and _KEYED.search(ln) for ln in _lines(text))


def _is_ext(name: str) -> bool:
    return name.lower().endswith(SCHEMA_EXT)


def _stem(name: str) -> str:
    return re.sub(r"\.(txt|dbml)$", "", name, flags=re.IGNORECASE)


def has_sidecar(file: Path) -> bool:
    """A layout sidecar next to the file: its own (`shop.layout.json`) or its folder's (`qdbd.layout.json`)."""
    return (file.parent / (_stem(file.name) + ".layout.json")).exists() or (file.parent / "qdbd.layout.json").exists()


def schema_language(file: Path, text: str, auto_detect: bool = True) -> str | None:
    """ "dbml", "quickdbd", or None when the file isn't a schema (the extension's test for opening a .txt)."""
    if file.name.lower().endswith(".dbml"):
        return "dbml"
    dbml = syntax_of(file.name, "\n".join(_lines(text))) == "dbml"
    if has_sidecar(file):
        return "dbml" if dbml else "quickdbd"
    if not auto_detect:
        return None
    return "dbml" if dbml else "quickdbd" if looks_like_quickdbd(text) else None


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _all_schemas(folder: Path) -> bool:
    """Every .txt under the folder has a table (or is DBML), and no layout file below marks a separate project."""
    seen = 0

    def walk(d: Path) -> bool:
        nonlocal seen
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return False
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                if e.name.startswith(".") or e.name == "node_modules" or not walk(Path(e.path)):
                    return False
            elif e.is_file(follow_symlinks=False) and e.name.lower().endswith(".layout.json"):
                return False  # a project of its own
            elif e.is_file(follow_symlinks=False) and _is_ext(e.name):
                seen += 1
                if seen > MAX_SCAN:
                    return False
                if e.name.lower().endswith(".dbml"):
                    continue
                text = _read(Path(e.path))
                if text.strip() and not has_table(text) and syntax_of(e.name, text) != "dbml":
                    return False
        return True

    return walk(folder)


def find_target(file: Path, stop_at: Path | None = None) -> tuple[Path, tuple[str, ...]]:
    """(cwd, paths) for a schema file:

    1. `<stem>.layout.json` next to the file: just that file.
    2. `qdbd.layout.json` in its folder or a parent (up to `stop_at`): that folder.
    3. An all-schema folder (see _all_schemas): the folder.
    4. Otherwise just the file.
    """
    folder, base = file.parent, file.name
    if (folder / (_stem(base) + ".layout.json")).exists():
        return folder, (base,)
    top = stop_at.resolve() if stop_at else folder.resolve()
    d = folder.resolve()
    while True:
        if (d / "qdbd.layout.json").exists():
            return d, (".",)
        if d == top or d.parent == d or not d.is_relative_to(top):
            break
        d = d.parent
    return (folder, (".",)) if _all_schemas(folder) else (folder, (base,))


def target_title(root: Path, paths: tuple[str, ...]) -> str:
    """The file's stem, or the folder's name."""
    return root.name if paths[0] == "." else _stem(PurePath(paths[0]).name)


@dataclass(frozen=True)
class Target:
    name: str  # unique within one Discovery
    kind: str  # "schema" or "dbt"
    root: Path  # absolute folder
    paths: tuple[str, ...]  # relative to root: (".",) or ("shop.txt",); dbt: ("target/manifest.json",)
    generated: bool = False  # schema files written by `qdbd import dbt`

    def inputs(self) -> list[Path]:
        return [self.root / p for p in self.paths]


@dataclass
class Discovery:
    targets: list[Target]
    truncated: str | None = None  # why the walk stopped early


def _generated(cwd: Path, paths: tuple[str, ...]) -> bool:
    files = [cwd / p for p in paths if p != "."] or [
        f for f in sorted(cwd.rglob("*")) if f.is_file() and _is_ext(f.name)
    ]
    return bool(files) and all(_read(f).startswith(HEADER) for f in files[:50])


def find_targets(root: Path, max_dirs: int = 20_000, max_seconds: float = 2.0) -> Discovery:
    """Every schema project under ``root``: groups of schema files (find_target) and dbt projects with a manifest."""
    root = root.resolve()
    start = time.monotonic()
    found: dict[tuple[Path, tuple[str, ...]], str] = {}  # (cwd, paths) -> kind
    truncated = None
    candidates = dirs = 0
    stack = [root]
    while stack:
        d = stack.pop()
        dirs += 1
        if dirs > max_dirs or time.monotonic() - start > max_seconds:
            truncated = f"stopped after {dirs - 1} folders; start qdbd mcp in a narrower folder or pass a path"
            break
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        sub = []
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                if not e.name.startswith(".") and e.name not in SKIP:
                    sub.append(Path(e.path))
                continue
            if e.is_symlink():
                try:
                    if not Path(e.path).resolve().is_relative_to(root):
                        continue
                except OSError:
                    continue
            if not e.is_file():
                continue
            if e.name == "dbt_project.yml":
                if (d / "target" / "manifest.json").is_file():
                    found.setdefault((d, ("target/manifest.json",)), "dbt")
                continue
            if not _is_ext(e.name):
                continue
            candidates += 1
            if candidates > MAX_FILES:
                truncated = f"stopped after {MAX_FILES} schema-like files"
                stack = []
                break
            p = Path(e.path)
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            if schema_language(p, _read(p)) is None:
                continue
            found.setdefault(find_target(p, root), "schema")
        stack.extend(reversed(sub))

    def title(cwd: Path, paths: tuple[str, ...], kind: str) -> str:
        return target_title(cwd, (".",) if kind == "dbt" else paths) + (" (dbt)" if kind == "dbt" else "")

    counts: dict[str, int] = {}
    for (cwd, paths), kind in found.items():
        counts[title(cwd, paths, kind)] = counts.get(title(cwd, paths, kind), 0) + 1
    targets = []
    for (cwd, paths), kind in found.items():
        name = title(cwd, paths, kind)
        if counts[name] > 1:
            rel = PurePath(os.path.relpath(cwd / paths[0] if kind == "schema" else cwd, root)).as_posix()
            name = rel + (" (dbt)" if kind == "dbt" else "")
        gen = kind == "schema" and _generated(cwd, paths)
        targets.append(Target(name, kind, cwd, paths, gen))
    return Discovery(sorted(targets, key=lambda t: t.name.lower()), truncated)
