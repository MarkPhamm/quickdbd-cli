"""`# @dbt: PATH`: descriptions, tags and types from a dbt project's yml, for hand-written schema files.

No manifest.json is needed (dbt Cloud projects have none locally). qdbd reads ``dbt_project.yml`` and the yml, md
and sql files under its resource paths (the root project only; ``dbt_packages/`` and ``target/`` are skipped).

- Tables match models, seeds, snapshots and sources (``source_name.table_name``) by name, ignoring case;
  columns match by name inside the matched table. ``# @dbt: none`` above a table opts it out.
- The dbt description is shown before the schema file's own comment; ``{{ doc('x') }}`` is filled from
  ``{% docs x %}`` blocks. Model and column tags rank below ``# @tag:`` and name prefixes. ``data_type`` fills
  columns that have no type.
- Drift is reported as warnings (``--strict`` fails on them): a table dbt doesn't have, a column only one side has,
  a type that differs (by base type: ``varchar(50)`` and ``string`` agree).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .dbt import node_tags, norm_type
from .model import DbtInfo, Schema

SKIP_DIRS = {"dbt_packages", "dbt_modules", "target", "logs", "node_modules"}
WATCHED = (".yml", ".yaml", ".md", ".sql", ".py", ".csv")
_DOC_REF = re.compile(r"""\{\{\s*doc\(\s*(?:['"][^'"]*['"]\s*,\s*)?['"]([^'"]+)['"]\s*\)\s*\}\}""")
_DOCS_BLOCK = re.compile(r"\{%-?\s*docs\s+([\w.-]+)\s*-?%\}(.*?)\{%-?\s*enddocs\s*-?%\}", re.S)
_SNAPSHOT = re.compile(r"\{%-?\s*snapshot\s+(\w+)\s*-?%\}")

# Base types that mean the same thing across warehouses; sizes and precision are ignored.
_FAMILIES = {
    "int": "int integer int2 int4 int8 int16 int32 int64 smallint bigint tinyint byteint mediumint hugeint long short",
    "decimal": "decimal numeric number dec bignumeric",
    "float": "float float4 float8 float32 float64 double double_precision real",
    "string": "string text varchar char character nvarchar nchar bpchar varchar2 nvarchar2 citext clob",
    "bool": "bool boolean",
    "timestamp": "timestamp timestamptz datetime datetime2 smalldatetime datetimeoffset timestamp_ntz timestamp_ltz "
    "timestamp_tz",
    "time": "time timetz",
    "json": "json jsonb variant object super",
    "binary": "binary varbinary bytes bytea blob",
    "uuid": "uuid uniqueidentifier",
    "array": "array list",
}
_BASE = {name: family for family, names in _FAMILIES.items() for name in names.split()}


class DbtError(Exception):
    pass


@dataclass
class DbtColumn:
    name: str
    description: str
    data_type: str | None
    tags: list[str]
    line: int


@dataclass
class DbtModel:
    name: str  # model / seed / snapshot name, or `source_name.table_name`
    description: str
    tags: list[str]
    columns: dict[str, DbtColumn]  # by lowercased name
    path: str  # yml file, relative to the project root
    line: int


@dataclass
class DbtProject:
    root: Path
    models: dict[str, DbtModel] = field(default_factory=dict)  # by lowercased name
    known: set[str] = field(default_factory=set)  # lowercased names that exist as files, documented or not
    ambiguous: set[str] = field(default_factory=set)
    docs: dict[str, str] = field(default_factory=dict)  # `{% docs name %}` blocks


class _Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):  # type: ignore[misc]
    """Records each mapping's line as `__line__`, so drift messages can point into the yml."""

    def construct_mapping(self, node, deep=False):
        m = super().construct_mapping(node, deep=deep)
        m["__line__"] = node.start_mark.line + 1
        return m


# (path, parser) -> (mtime_ns, parsed): keeps `qdbd serve` recompiles cheap
_cache: dict[tuple[Path, Callable], tuple[int, object]] = {}


def _cached(path: Path, parse: Callable[[str], object]) -> object:
    mtime = path.stat().st_mtime_ns
    hit = _cache.get((path, parse))
    if hit is None or hit[0] != mtime:
        hit = _cache[(path, parse)] = (mtime, parse(path.read_text(encoding="utf-8")))
    return hit[1]


def _load_yaml(text: str) -> object:
    return yaml.load(text, Loader=_Loader)  # a SafeLoader: no arbitrary Python objects


def _yaml(path: Path, root: Path) -> object:
    try:
        return _cached(path, _load_yaml)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"{path.relative_to(root).as_posix()}:{mark.line + 1}" if mark else path.relative_to(root).as_posix()
        raise DbtError(f"{where}: invalid YAML ({getattr(e, 'problem', None) or e})") from None


def find_root(path: Path) -> Path:
    """The dbt project a `# @dbt:` path names: its folder, or its dbt_project.yml."""
    root = path.parent if path.name == "dbt_project.yml" else path
    if not (root / "dbt_project.yml").is_file():
        raise DbtError(f"no dbt_project.yml in {root}")
    return root


def _paths(root: Path) -> tuple[dict[str, list[Path]], list[Path]]:
    """(resource kind -> folders, docs folders), from dbt_project.yml with dbt's defaults."""
    cfg = _yaml(root / "dbt_project.yml", root)
    cfg = cfg if isinstance(cfg, dict) else {}

    def get(key: str, old: str | None, default: str) -> list[Path]:
        v = cfg.get(key) or (cfg.get(old) if old else None) or [default]
        return [root / p for p in ([v] if isinstance(v, str) else v)]

    kinds = {
        "model": get("model-paths", "source-paths", "models"),
        "seed": get("seed-paths", "data-paths", "seeds"),
        "snapshot": get("snapshot-paths", None, "snapshots"),
    }
    docs = cfg.get("docs-paths")
    if docs:
        doc_dirs = [root / p for p in ([docs] if isinstance(docs, str) else docs)]
    else:  # dbt's default: every resource path
        doc_dirs = [d for ds in kinds.values() for d in ds]
        doc_dirs += get("analysis-paths", None, "analyses") + get("macro-paths", None, "macros")
    return kinds, doc_dirs


def _walk(dirs: list[Path], suffixes: tuple[str, ...]) -> list[Path]:
    out: dict[Path, None] = {}
    for d in dirs:
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = sorted(n for n in dirnames if not n.startswith(".") and n not in SKIP_DIRS)
            for n in sorted(filenames):
                if n.lower().endswith(suffixes):
                    out[Path(dirpath, n)] = None
    return list(out)


def watched_files(root: Path) -> list[Path]:
    """Every file `load_project` reads (or may read once it exists), for `qdbd serve`'s change polling."""
    kinds, doc_dirs = _paths(root)
    return [root / "dbt_project.yml", *_walk([d for ds in kinds.values() for d in ds] + doc_dirs, WATCHED)]


def _text(v: object) -> str:
    return str(v).strip() if v is not None else ""


def _column_name(v: object) -> str:
    return _text(v).strip('"`')


def load_project(root: Path) -> DbtProject:
    kinds, doc_dirs = _paths(root)
    project = DbtProject(root)
    for p in _walk(kinds["model"], (".sql", ".py")):
        project.known.add(p.stem.lower())
    for p in _walk(kinds["seed"], (".csv",)):
        project.known.add(p.stem.lower())
    for p in _walk(kinds["snapshot"], (".sql",)):
        project.known.update(m.lower() for m in _cached(p, _SNAPSHOT.findall))  # type: ignore[union-attr]
    for p in _walk(doc_dirs, (".md",)):
        for name, body in _cached(p, _DOCS_BLOCK.findall):  # type: ignore[union-attr]
            project.docs[name] = body.strip()
    for p in _walk([d for ds in kinds.values() for d in ds], (".yml", ".yaml")):
        data = _yaml(p, root)
        if not isinstance(data, dict):
            continue
        rel = p.relative_to(root).as_posix()
        for key in ("models", "seeds", "snapshots"):
            for n in data.get(key) or []:
                if isinstance(n, dict) and n.get("name"):
                    _add(project, _text(n["name"]), n, rel)
        for src in data.get("sources") or []:
            if not isinstance(src, dict) or not src.get("name"):
                continue
            for n in src.get("tables") or []:
                if isinstance(n, dict) and n.get("name"):
                    _add(project, f"{_text(src['name'])}.{_text(n['name'])}", n, rel)
    return project


def _add(project: DbtProject, name: str, n: dict, rel: str) -> None:
    key = name.lower()
    if key in project.models:
        project.ambiguous.add(key)
        return
    cols: dict[str, DbtColumn] = {}
    for c in n.get("columns") or []:
        if isinstance(c, dict) and _column_name(c.get("name")):
            cname = _column_name(c["name"])
            dtype = _text(c.get("data_type")) or None
            cols[cname.lower()] = DbtColumn(cname, _text(c.get("description")), dtype, node_tags(c), c["__line__"])
    project.models[key] = DbtModel(name, _text(n.get("description")), node_tags(n), cols, rel, n["__line__"])
    project.known.add(key)


def base_type(t: str) -> str:
    """`varchar(255)` -> `string`, `INTEGER` -> `int`: what two types must share to count as the same."""
    s = re.split(r"[(<\[]", (norm_type(t) or "").lower())[0].strip("_ ")
    return _BASE.get(s, s)


Report = Callable[[str, int, str, str], None]  # (path, line, message, severity)


def apply(schema: Schema, project: DbtProject, report: Report) -> None:
    """Attach dbt descriptions, tags and types to the matching tables and columns, and report drift."""

    def doc(text: str, path: str, line: int) -> str:
        def sub(m: re.Match) -> str:
            if m.group(1) in project.docs:
                return project.docs[m.group(1)]
            report(path, line, f"dbt: no docs block named '{m.group(1)}'", "warning")
            return m.group(0)

        return _DOC_REF.sub(sub, text)

    for t in schema.tables.values():
        key = t.name.lower()
        if t.dbt_skip or key in project.ambiguous:
            continue
        m = project.models.get(key)
        if m is None:
            if key not in project.known:
                report(
                    t.path,
                    t.line,
                    f"dbt: no model, seed, snapshot or source named '{t.name}' "
                    "(put '# @dbt: none' above the table if it isn't one)",
                    "warning",
                )
            continue
        t.dbt = DbtInfo(doc(m.description, t.path, t.line), list(m.tags))
        cols = {c.name.lower(): c for c in t.columns.values() if not c.virtual}
        for ckey, dc in m.columns.items():
            c = cols.get(ckey)
            if c is None:
                msg = f"dbt: column '{dc.name}' ({m.path}:{dc.line}) is missing from '{t.name}'"
                report(t.path, t.line, msg, "warning")
                continue
            c.dbt = DbtInfo(doc(dc.description, t.path, c.line), list(dc.tags), norm_type(dc.data_type))
            if dc.data_type and c.type and not c.type_default and base_type(c.type) != base_type(dc.data_type):
                msg = f"dbt: type '{c.type}' differs from data_type '{dc.data_type}' ({m.path}:{dc.line})"
                report(t.path, c.line, msg, "warning")
        if m.columns:
            for ckey, c in cols.items():
                if ckey not in m.columns:
                    msg = f"dbt: column '{c.name}' is not in the yml for '{m.name}' ({m.path}:{m.line})"
                    report(t.path, c.line, msg, "warning")
