"""The tools `qdbd mcp` gives AI agents: read-only questions about the compiled schema, answered as compact text.

Each tool is a plain function over a Workspace (the schema projects found under the server's root), so tests call
them directly; mcp.py only speaks the protocol. Results stay under one character budget and say what they left out.
"""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path, PurePath

from . import diff, export, layout
from .dbt import HEADER, DbtImportError, ImportResult, import_dbt
from .jsrt import JSTimeout, runtime
from .measure import model_json
from .model import VIRTUAL_FIELD, Relationship, Schema
from .parser import FileParse, compile_files
from .project import discover, display_path
from .targets import Discovery, Target, find_targets

BUDGET = 40_000  # characters per result; Claude Code moves results over 50k into a file
CARD = {"one": "1", "many": "N", "zeroOne": "0..1", "zeroMany": "0..N"}
MANY = ("many", "zeroMany")
JS_TIMEOUT = 10.0
LAYOUT_TIMEOUT = 60.0
MAX_ARG = 500
DIAGRAM_LIMITS = {"full": 30, "keys": 60, "header": 100}
IMAGE_SIDE = 1568  # Claude scales larger images down
MIN_SCALE = 0.6


class ToolError(Exception):
    """A failure the agent can act on; reported as an error result, not a protocol error."""


@dataclass
class Result:
    text: str
    image: bytes | None = None  # PNG
    error: bool = False


@dataclass
class Compiled:
    target: Target
    sources: list[tuple[str, str]]
    schema: Schema
    files: list[FileParse]
    model: dict
    dbt: ImportResult | None = None
    by_id: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_id = {t["id"]: t for t in self.model["tables"]}


def posix(p: str) -> str:
    return PurePath(p).as_posix()


def clip(lines: list[str], noun: str, budget: int = BUDGET) -> list[str]:
    """Keep whole lines within the budget; say how many were dropped."""
    out, used = [], 0
    for i, line in enumerate(lines):
        used += len(line) + 1
        if used > budget:
            return out + [f"…and {len(lines) - i} more {noun}; narrow with `select` or a more specific query."]
        out.append(line)
    return out


def _js(fn: str, *args, timeout: float = JS_TIMEOUT):
    rt = runtime()
    rt.load("render.js")
    try:
        return rt.call(fn, *args, timeout_sec=timeout)
    except JSTimeout:
        raise ToolError("that took too long; simplify the selector or narrow the request") from None
    except ToolError:
        raise
    except Exception as e:  # JS exceptions: "<anonymous>:N: Error: message"
        raise ToolError(re.sub(r"^.*?Error: ", "", str(e).splitlines()[0])) from None


def _arg(value, name: str, limit: int = MAX_ARG) -> str:
    if value is not None and len(str(value)) > limit:
        raise ToolError(f"`{name}` is too long (at most {limit} characters)")
    return value


# --------------------------------------------------------------------------- projects


class Workspace:
    """The schema projects a server answers about: one given on the command line, or every one found under root."""

    def __init__(
        self, root: Path, fixed: Target | None = None, infer_fks: bool = False, refused: str | None = None
    ) -> None:
        self.root = root.resolve()
        self.fixed = fixed
        self.infer_fks = infer_fks
        self.refused = refused
        self._found: Discovery | None = None
        self._found_at = 0.0
        self._cache: dict[Target, tuple[tuple, Compiled]] = {}

    def discovery(self, refresh: bool = False) -> Discovery:
        if self.refused:
            raise ToolError(self.refused)
        if self.fixed:
            return Discovery([self.fixed])
        if refresh or self._found is None or time.monotonic() - self._found_at > 5:
            self._found, self._found_at = find_targets(self.root), time.monotonic()
        return self._found

    def target(self, name: str | None) -> Target:
        _arg(name, "project")
        for refresh in (False, True):
            ts = self.discovery(refresh).targets
            if not ts:
                break
            if name is None:
                if len(ts) == 1:
                    return ts[0]
                raise ToolError(
                    f"{len(ts)} projects here; pass `project` (one of: {', '.join(t.name for t in ts)}). "
                    "Database schemas such as sales.* are filtered with `select` instead."
                )
            for t in ts:
                if t.name == name or t.name.lower() == name.lower():
                    return t
        names = [t.name for t in self.discovery().targets]
        if not names:
            raise ToolError(
                f"no schema files (.txt, .dbml) or dbt projects found under {self.root}; "
                "start qdbd mcp with --root DIR or a schema path"
            )
        raise ToolError(f"no project '{name}'; projects: {', '.join(names)}")

    def compile(self, t: Target, overrides: dict[Path, str] | None = None) -> Compiled:
        if t.kind == "dbt":
            return self._compile_dbt(t)
        try:
            files = discover(t.inputs())
        except FileNotFoundError as e:
            raise ToolError(str(e)) from None
        bound = t.root.resolve()
        files = [f for f in files if not f.is_symlink() or f.resolve().is_relative_to(bound)]
        over = {p.resolve(): text for p, text in (overrides or {}).items()}
        files += [p for p in over if p not in {f.resolve() for f in files}]
        key = tuple((str(f), *_stat(f)) for f in files)
        hit = self._cache.get(t)
        if not over and hit and hit[0] == key:
            return hit[1]
        sources = []
        for f in files:
            text = over.get(f.resolve())
            if text is None:
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    raise ToolError(f"can't read {posix(display_path(f))}: {e}") from None
            sources.append((posix(display_path(f)), text))
        schema, fps = compile_files(sources)
        c = Compiled(t, sources, schema, fps, model_json(schema))
        if not over:
            self._cache[t] = (key, c)
        return c

    def _compile_dbt(self, t: Target) -> Compiled:
        manifest = t.inputs()[0]
        key = tuple((str(f), *_stat(f)) for f in (manifest, manifest.parent / "catalog.json"))
        hit = self._cache.get(t)
        if hit and hit[0] == key:
            return hit[1]
        try:
            res = import_dbt(manifest, split=True, infer_fks=self.infer_fks)
        except DbtImportError as e:
            raise ToolError(str(e)) from None
        label = t.name.removesuffix(" (dbt)")
        sources = [(f"<dbt:{label}>/{name}", text) for name, text in res.files.items()]
        schema, fps = compile_files(sources)
        c = Compiled(t, sources, schema, fps, model_json(schema), res)
        self._cache[t] = (key, c)
        return c

    def overrides(self, t: Target, file: str | None, content: str | None) -> dict[Path, str] | None:
        """``content`` stands in for ``file`` (one of the project's files, or a new one in its folder)."""
        if content is None:
            if file is not None:
                raise ToolError("`file` goes with `content` (the unsaved text to check)")
            return None
        if t.kind == "dbt":
            raise ToolError("dbt projects are read from the manifest; edit the dbt YAML instead")
        if not file:
            files = discover(t.inputs())
            if len(files) != 1:
                raise ToolError("pass `file`: which of the project's files `content` replaces")
            return {files[0]: content}
        p = Path(_arg(file, "file"))
        p = (p if p.is_absolute() else Path.cwd() / p).resolve()
        known = {f.resolve() for f in discover(t.inputs())}
        folders = [i.resolve() for i in t.inputs() if i.is_dir()]
        if p not in known and not (p.suffix.lower() in (".txt", ".dbml") and any(p.is_relative_to(d) for d in folders)):
            raise ToolError(f"{file} is not one of this project's schema files (or a new .txt/.dbml in its folder)")
        return {p: content}


def _stat(f: Path) -> tuple[int, int]:
    try:
        st = f.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return 0, -1


# --------------------------------------------------------------------------- shared formatting


def _clean_name(name: str) -> str:
    parts = re.split(r"\.(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", name.strip())  # dots outside quotes
    return ".".join(p.strip().strip('"`').removeprefix("[").removesuffix("]") for p in parts)


def find_table(c: Compiled, name: str) -> dict | None:
    for cand in dict.fromkeys([name, _clean_name(name)]):
        for n in (cand, cand[7:] if cand.lower().startswith("public.") else None):
            t = n and export.find_table(c.model, n)
            if t:
                return t
    return None


def need_table(c: Compiled, name: str) -> dict:
    _arg(name, "table")
    t = find_table(c, name)
    if t is None:
        names = [x["name"] for x in c.model["tables"]]
        close = difflib.get_close_matches(name, names, n=3, cutoff=0.5) or difflib.get_close_matches(
            name.lower(), [n.lower() for n in names], n=3, cutoff=0.5
        )
        hint = f" Closest: {', '.join(close)}." if close else " Try search_schema."
        raise ToolError(f"no table '{name}' in {c.target.name}.{hint}")
    return t


def selected(c: Compiled, select: str | None) -> list[dict]:
    """Tables matching a dbt-style selector (all when empty); a selector that is just a table's name is that table."""
    if not select or not select.strip():
        return c.model["tables"]
    _arg(select, "select")
    t = find_table(c, select)
    if t is not None:
        return [t]
    ids = _js("qdbdSelect", c.model, select)
    if not ids:
        raise ToolError(f"no tables match '{select}'")
    keep = set(ids)
    return [t for t in c.model["tables"] if t["id"] in keep]


def _col(t: dict, cid: str) -> dict | None:
    return next((x for x in t["cols"] if x["id"] == cid), None)


def _child_parent(r: dict) -> tuple[dict, dict]:
    a_child = r["a"]["card"] in MANY or r["b"]["card"] not in MANY
    return (r["a"], r["b"]) if a_child else (r["b"], r["a"])


def _end(c: Compiled, e: dict, cols: list[str] | None = None) -> str:
    t = c.by_id[e["t"]]
    cols = cols if cols is not None else ([] if e["c"] == VIRTUAL_FIELD else [e["c"]])
    names = [x["name"] for k in cols if (x := _col(t, k))]
    if not names:
        return t["name"]
    return f"{t['name']}.{names[0]}" if len(names) == 1 else f"{t['name']}.({', '.join(names)})"


def _inferred(c: Compiled) -> set[str]:
    return set(c.dbt.inferred) if c.dbt else set()


def _loc(c: Compiled, r: Relationship) -> str:
    return "" if c.target.kind == "dbt" else f"  [{r.path}:{r.line}]"


def rel_lines(c: Compiled, table_id: str) -> tuple[list[str], list[str]]:
    """'References' and 'Referenced by' lines for a table; composite keys as one line."""
    valid = c.schema.valid_relationships()
    inferred = _inferred(c)
    refs, back, done = [], [], set()
    for i, r in enumerate(c.model["rels"]):
        if "k" in r:
            if r["k"] in done:
                continue
            done.add(r["k"])
            group = [x for x in c.model["rels"] if x.get("k") == r["k"]]
        else:
            group = [r]
        child, parent = _child_parent(r)
        if table_id not in (child["t"], parent["t"]):
            continue
        cc = [_child_parent(x)[0]["c"] for x in group if _child_parent(x)[0]["c"] != VIRTUAL_FIELD]
        pc = [_child_parent(x)[1]["c"] for x in group if _child_parent(x)[1]["c"] != VIRTUAL_FIELD]
        text = f"{_end(c, child, cc)} -> {_end(c, parent, pc)} ({CARD[child['card']]}:{CARD[parent['card']]})"
        tags = []
        if not cc:
            tags.append("table-level: no join columns declared")
        if len(group) > 1:
            tags.append("composite key")
        if text.split(" (")[0] in inferred:
            tags.append("inferred from column names")
        line = text + (f" — {'; '.join(tags)}" if tags else "") + _loc(c, valid[i])
        if child["t"] == table_id:
            refs.append(line)
        if parent["t"] == table_id:
            back.append(line)
    return refs, back


def _header(c: Compiled) -> list[str]:
    out = []
    if c.schema.errors:
        out.append(
            f"Note: {c.target.name} has {len(c.schema.errors)} error(s); results cover what parsed. Run check_schema."
        )
    return out


# --------------------------------------------------------------------------- tools


def list_projects(ws: Workspace, args: dict) -> Result:
    d = ws.discovery(refresh=True)
    if not d.targets:
        raise ToolError(
            f"no schema files (.txt, .dbml) or dbt projects found under {ws.root}; "
            "start qdbd mcp with --root DIR or a schema path"
        )
    lines = [f"{len(d.targets)} project(s) under {posix(str(ws.root))}:"]
    for t in d.targets[:50]:
        try:
            c = ws.compile(t)
        except ToolError as e:
            lines.append(f"- {t.name}: can't read it: {e}")
            continue
        s = c.schema
        where = posix(display_path(t.inputs()[0])) if t.kind == "schema" else posix(display_path(t.inputs()[0]))
        kind = "dbt manifest (live)" if t.kind == "dbt" else "schema files"
        if t.generated:
            kind = "generated by `qdbd import dbt`: edit the dbt YAML and re-run the import, don't hand-edit"
        lines.append(
            f"- {t.name} — {kind}; {where}; {len(s.tables)} tables, {len(s.valid_relationships())} relationships, "
            f"{len(s.errors)} error(s), {len(s.warnings)} warning(s)"
        )
        if t.kind == "schema":
            for fp in c.files[:20]:
                lines.append(f"    {fp.path} ({fp.syntax}, {len(fp.tables)} tables)")
            if len(c.files) > 20:
                lines.append(f"    …and {len(c.files) - 20} more files")
        if c.dbt:
            if c.dbt.tables and not c.dbt.relationships:
                lines.append(
                    "    no relationships: add `relationships` tests or foreign_key constraints in dbt"
                    + ("" if ws.infer_fks else ", or start qdbd mcp with --infer-fks")
                )
            if c.dbt.inferred:
                lines.append(f"    {len(c.dbt.inferred)} relationship(s) inferred from column names (--infer-fks)")
            if c.dbt.no_columns and not c.dbt.catalog:
                lines.append(f"    {c.dbt.no_columns} tables have no known columns: run `dbt docs generate`")
    if len(d.targets) > 50:
        lines.append(f"…and {len(d.targets) - 50} more projects")
    if d.truncated:
        lines.append(f"Search incomplete: {d.truncated}.")
    if len(d.targets) > 1:
        lines.append("Pass `project` (the name before the dash) to the other tools.")
    return Result("\n".join(clip(lines, "lines")))


def list_tables(ws: Workspace, args: dict) -> Result:
    c = ws.compile(ws.target(args.get("project")))
    select = args.get("select")
    tables = selected(c, select)
    head = _header(c) + [f"{len(tables)} table(s) in {c.target.name}" + (f" matching '{select}'" if select else "")]
    groups: dict[str, list[dict]] = {}
    for t in tables:
        groups.setdefault(t.get("group") or "", []).append(t)
    lines = []
    if len(tables) > 300 and not select:
        lines.append("Too many to list; tables per group (use `select`, e.g. group:NAME, to list one):")
        for g, ts in groups.items():
            sample = ", ".join(t["name"] for t in ts[:5])
            lines.append(f"- {g or '(no group)'}: {len(ts)} tables, e.g. {sample}")
        return Result("\n".join(head + clip(lines, "groups")))
    for g, ts in groups.items():
        if len(groups) > 1 or g:
            lines.append(f"[{g or 'no group'}]")
        for t in ts:
            alias = f" (as {', '.join(t['aliases'])})" if t["aliases"] else ""
            doc = (t.get("doc") or "").split("\n")[0]
            lines.append(f"- {t['name']}{alias}: {len(t['cols'])} columns" + (f" — {doc}" if doc else ""))
    return Result("\n".join(head + clip(lines, "tables")))


def _enums(c: Compiled) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fp in c.files:
        out.update(fp.enums)
    return out


def _generated_files(c: Compiled) -> set[str]:
    return {p for p, text in c.sources if text.startswith(HEADER)}


def describe_tables(ws: Workspace, args: dict) -> Result:
    c = ws.compile(ws.target(args.get("project")))
    names, select = args.get("tables") or [], args.get("select")
    if not names and not select:
        raise ToolError("pass `tables` (names) or `select` (a selector)")
    tables, unknown = [], []
    for n in names:
        try:
            tables.append(need_table(c, n))
        except ToolError as e:
            unknown.append(str(e))
    if select:
        tables += [t for t in selected(c, select) if t not in tables]
    out = _header(c) + unknown
    if len(tables) > 25:
        out.append(f"{len(tables)} tables match; showing the first 25 (narrow with `select`).")
        tables = tables[:25]
    enums, gen = _enums(c), _generated_files(c)
    inferred = _inferred(c)
    for t in tables:
        st = c.schema.tables[t["id"]]
        alias = f" (as {', '.join(t['aliases'])})" if t["aliases"] else ""
        meta = [] if c.target.kind == "dbt" else [f"{t['file']}:{t['line']}"]
        if t.get("group"):
            meta.append(f"group {t['group']}")
        if t.get("tags"):
            meta.append(f"tags {', '.join(t['tags'])}")
        out.append(f"## {t['name']}{alias}  " + "  ".join(meta))
        if st.path in gen:
            out.append("(generated by `qdbd import dbt`: edit the dbt YAML and re-run the import)")
        if t.get("doc"):
            out.append(t["doc"])
        fks: dict[str, list[str]] = {}
        for r in c.model["rels"]:
            child, parent = _child_parent(r)
            for here, there in ((child, parent), (parent, child)):
                if here["t"] == t["id"] and here["c"] != VIRTUAL_FIELD and there["c"] != VIRTUAL_FIELD:
                    if here is child:
                        target = _end(c, there)
                        tag = " (inferred)" if f"{_end(c, here)} -> {target}" in inferred else ""
                        fks.setdefault(here["c"], []).append(f"FK -> {target}{tag}")
        out.append("Columns:")
        cols = t["cols"]
        for col in cols[:60]:
            flags = [f for f, on in (("PK", col["pk"]), ("unique", col["unique"]), ("index", col["index"])) if on]
            flags += fks.get(col["id"], [] if not col["fk"] else ["FK"])
            if col["nullable"]:
                flags.append("null")
            if col["identity"]:
                flags.append("auto")
            if col["default"] is not None:
                flags.append(f"default={col['default']}")
            if col["type"] in enums:
                vals = enums[col["type"]]
                flags.append("enum(" + ", ".join(vals[:20]) + (", …" if len(vals) > 20 else "") + ")")
            line = "" if c.target.kind == "dbt" else f"  (line {st.columns[col['id']].line})"
            doc = f" — {col['doc']}" if col.get("doc") else ""
            out.append(f"- {col['name']} {col['type'] or '?'}" + (f" {', '.join(flags)}" if flags else "") + doc + line)
        if len(cols) > 60:
            out.append(f"…and {len(cols) - 60} more columns")
        refs, back = rel_lines(c, t["id"])
        out += ["References:"] + [f"- {x}" for x in refs] if refs else ["References: none"]
        out += ["Referenced by:"] + [f"- {x}" for x in back] if back else ["Referenced by: none"]
        out.append("")
    return Result("\n".join(clip(out, "lines")).rstrip(), error=not tables)


def _matcher(query: str):
    q = query.strip()
    if "*" in q or "?" in q:
        rx = re.compile(re.escape(re.sub(r"\*+", "*", q)).replace(r"\*", ".*").replace(r"\?", "."), re.IGNORECASE)
        return lambda s: bool(s) and bool(rx.search(s))
    low = q.lower()
    return lambda s: bool(s) and low in s.lower()


def search_schema(ws: Workspace, args: dict) -> Result:
    query = _arg(args.get("query") or "", "query")
    if not query.strip():
        raise ToolError("pass a `query`")
    c = ws.compile(ws.target(args.get("project")))
    hit = _matcher(query)
    tables, cols, docs = [], [], []
    for t in c.model["tables"]:
        if hit(t["name"]) or any(hit(a) for a in t["aliases"]):
            tables.append(f"- {t['name']}")
        if hit(t.get("doc", "")):
            docs.append(f"- {t['name']}: {t['doc'].splitlines()[0]}")
        for col in t["cols"]:
            if hit(col["name"]):
                keys = " PK" if col["pk"] else " FK" if col["fk"] else ""
                cols.append(f"- {t['name']}.{col['name']} {col['type'] or '?'}{keys}")
            if hit(col.get("doc", "")):
                docs.append(f"- {t['name']}.{col['name']}: {col['doc'].splitlines()[0]}")
    total = len(tables) + len(cols) + len(docs)
    if not total:
        return Result(f"Nothing in {c.target.name} matches '{query}'.")
    out = [f"{total} match(es) for '{query}' in {c.target.name}"]
    shown = 0
    for title, items in (("Tables", tables), ("Columns", cols), ("Docs", docs)):
        if items and shown < 100:
            keep = items[: 100 - shown]
            shown += len(keep)
            out += [f"{title}:"] + keep
    if shown < total:
        out.append(f"…and {total - shown} more; use a more specific query.")
    return Result("\n".join(clip(out, "matches")))


def _optional(c: Compiled, st: dict) -> bool:
    if "zero" in st["from"]["card"] or "zero" in st["to"]["card"]:
        return True
    for p in st["pairs"]:
        for side, cid in ((st["from"], p[0]), (st["to"], p[1])):
            col = _col(c.by_id[side["t"]], cid)
            if col and col["nullable"]:
                return True
    return False


def join_path(ws: Workspace, args: dict) -> Result:
    for k in ("from", "to"):
        if not args.get(k):
            raise ToolError(f"pass `{k}` (a table name)")
    c = ws.compile(ws.target(args.get("project")))
    a, b = need_table(c, args["from"]), need_table(c, args["to"])
    out = _header(c)
    steps = _js("qdbdFindPath", c.model, a["id"], b["id"])
    if steps is None:
        out.append(f"No relationship path between {a['name']} and {b['name']}.")
        if c.dbt and not c.dbt.relationships:
            out.append(
                "This dbt project declares no relationships: add `relationships` tests"
                + ("" if ws.infer_fks else ", or start qdbd mcp with --infer-fks")
                + "."
            )
        return Result("\n".join(out))
    if not steps:
        return Result("\n".join(out + [f"{a['name']} is the same table: no join needed."]))
    inferred, rels = _inferred(c), c.model["rels"]
    out.append(f"{a['name']} -> {b['name']}: {len(steps)} join(s)")
    for n, st in enumerate(steps, 1):
        pairs = st["pairs"]
        joined = f"{_end(c, st['from'], [p[0] for p in pairs])} -> {_end(c, st['to'], [p[1] for p in pairs])}"
        fc, tc = st["from"]["card"], st["to"]["card"]
        notes = []
        if not pairs:
            notes.append("table-level relationship: join columns not declared")
        if len(pairs) > 1:
            notes.append("composite key: join on every column")
        if _optional(c, st):
            notes.append("optional: LEFT JOIN keeps rows without a match")
        if fc in MANY and tc in MANY:
            notes.append("N:N: joined directly; check for a junction table")
        elif tc in MANY:
            notes.append("1:N: rows multiply")
        if joined in inferred or f"{_end(c, st['to'], [p[1] for p in pairs])} -> {joined.split(' -> ')[0]}" in inferred:
            notes.append("inferred from column names")
        out.append(f"{n}. {joined} ({CARD[fc]}:{CARD[tc]})" + (f" — {'; '.join(notes)}" if notes else ""))
        mine = rels[st["rel"]]
        pair = {st["from"]["t"], st["to"]["t"]}
        for r in rels:
            if r is mine or {r["a"]["t"], r["b"]["t"]} != pair or ("k" in mine and r.get("k") == mine["k"]):
                continue
            child, parent = _child_parent(r)
            alt = f"{_end(c, child)} -> {_end(c, parent)} ({CARD[child['card']]}:{CARD[parent['card']]})"
            if child["c"] == VIRTUAL_FIELD:
                alt += ", table-level: no join columns declared"
            out.append(f"   also joinable via {alt}")
    out += ["", _js("qdbdPathSql", c.model, a["id"], steps)]
    if c.target.kind == "dbt":
        out += ["", "In a dbt model, write {{ ref('model') }} / {{ source('source', 'table') }} for these names."]
    return Result("\n".join(out))


def check_schema(ws: Workspace, args: dict) -> Result:
    t = ws.target(args.get("project"))
    c = ws.compile(t, ws.overrides(t, args.get("file"), args.get("content")))
    s, strict = c.schema, bool(args.get("strict"))
    what = f"{len(c.sources)} file(s), {len(s.tables)} tables"
    if not s.diagnostics:
        return Result(f"OK: {what}, no errors or warnings.")
    lines = [d.format() for d in s.diagnostics[:200]]
    if len(s.diagnostics) > 200:
        lines.append(f"…and {len(s.diagnostics) - 200} more")
    failed = s.errors or (strict and s.warnings)
    verdict = "FAILED" if failed else "OK with warnings"
    summary = f"{verdict}: {what}, {len(s.errors)} error(s), {len(s.warnings)} warning(s)"
    return Result("\n".join([summary] + clip(lines, "diagnostics")))


def diff_schema(ws: Workspace, args: dict) -> Result:
    t = ws.target(args.get("project"))
    if t.kind == "dbt":
        raise ToolError(
            "a dbt manifest isn't in git; diff the files `qdbd import dbt` generates "
            "(commit them, then pass that project)"
        )
    base = _arg(args.get("base") or "HEAD", "base", 200)
    use_mb = args.get("merge_base")
    use_mb = base != "HEAD" if use_mb is None else bool(use_mb)
    c = ws.compile(t, ws.overrides(t, args.get("file"), args.get("content")))
    try:
        ref = diff.merge_base(base, t.inputs()) if use_mb else base
        old = diff.schema_at_ref(ref, t.inputs())
    except diff.DiffError as e:
        raise ToolError(str(e)) from None
    label = f"{base} (merge-base {ref[:7]})" if use_mb else base
    new_label = "unsaved edit" if args.get("content") is not None else "working tree"
    d = diff.diff_schemas(old, c.schema)
    if args.get("format") == "markdown":
        text = diff.format_markdown(d, label, new_label)
    else:
        text = diff.format_text(d, label, new_label)
    return Result("\n".join(clip(_header(c) + text.splitlines(), "lines")))


def _svg_size(svg: str) -> tuple[float, float]:
    w = re.search(r'\bwidth="([\d.]+)', svg)
    h = re.search(r'\bheight="([\d.]+)', svg)
    return (float(w.group(1)) if w else 1000.0, float(h.group(1)) if h else 1000.0)


def render_diagram(ws: Workspace, args: dict) -> Result:
    c = ws.compile(ws.target(args.get("project")))
    tables = selected(c, args.get("select"))
    ids = [t["id"] for t in tables]
    if args.get("focus"):
        keep = set(ids)
        sub = {**c.model, "rels": [r for r in c.model["rels"] if r["a"]["t"] in keep and r["b"]["t"] in keep]}
        sub["tables"] = tables
        f = need_table(c, args["focus"])
        if f["id"] not in keep:
            raise ToolError(f"{f['name']} isn't in the selection")
        depth = args.get("depth", 1)
        if not isinstance(depth, int) or not 0 <= depth <= 5:
            raise ToolError("`depth` is a number of hops from 0 to 5")
        ids = _js("qdbdNeighbourhood", sub, f["id"], depth)
    modes = ["full", "keys", "header"]
    start = modes.index(args.get("mode") or "full")
    n = len(ids)
    keep = set(ids)
    tables = [t for t in c.model["tables"] if t["id"] in keep]
    rels = [r for r in c.model["rels"] if r["a"]["t"] in keep and r["b"]["t"] in keep]
    if n > DIAGRAM_LIMITS["header"]:
        raise ToolError(f"{n} tables is too many for a readable image (at most 100); narrow with `select` or `focus`")
    try:
        pos = {k: [v[0], v[1]] for k, v in layout.elk_layout(tables, rels, timeout_sec=LAYOUT_TIMEOUT).items()}
    except JSTimeout:
        raise ToolError("the layout took too long; narrow with `select` or `focus`") from None
    for mode in modes[start:]:
        if n > DIAGRAM_LIMITS[mode]:
            continue
        svg = export.render_svg(c.model, pos, only=ids, mode=mode, embed_font=False)
        scale = min(2.0, IMAGE_SIDE / max(_svg_size(svg)))
        if scale >= MIN_SCALE:
            png = export.svg_to_png(svg, scale)
            names = ", ".join(t["name"] for t in tables[:40]) + (", …" if n > 40 else "")
            note = "" if mode == (args.get("mode") or "full") else f" (switched to {mode} mode to stay readable)"
            return Result(f"{n} table(s), {mode} mode{note}: {names}", image=png)
    raise ToolError(f"{n} tables won't fit in a readable image; narrow with `select` or `focus`")


def syntax_reference(ws: Workspace, args: dict) -> Result:
    text = resources.files("quickdbd_cli").joinpath("assets/syntax-reference.md").read_text(encoding="utf-8")
    want = args.get("syntax")
    if want:
        parts = re.split(r"(?m)^(?=# )", text)
        keep = [p for p in parts if not p.startswith("# ") or (("DBML" in p.splitlines()[0]) == (want == "dbml"))]
        keep += [p for p in parts if p.startswith("# Notes")]
        text = "".join(dict.fromkeys(keep))
    return Result(text.strip())


# --------------------------------------------------------------------------- tool definitions

PROJECT = {
    "type": "string",
    "description": "Which project (a name from list_projects). Optional when there is only one. This is not a "
    "database schema: filter tables such as sales.* with `select`.",
    "maxLength": MAX_ARG,
}
SELECT = {
    "type": "string",
    "description": "dbt-style selector: a name or glob (`orders`, `fct_*`; case-insensitive; `?` matches one "
    "character, e.g. a space), `+orders` (and the tables it references), `orders+` (and the tables referencing it), "
    "`2+orders+1` (hops), methods `group:`, `file:`, `col:`, `tag:`. Space = union, comma = intersection, "
    "leading `!` = exclude.",
    "maxLength": MAX_ARG,
}
FILE = {
    "type": "string",
    "description": "With `content`: which schema file the text replaces (one of the project's files, or a new "
    ".txt/.dbml path in its folder). Nothing is written.",
    "maxLength": MAX_ARG,
}
CONTENT = {"type": "string", "description": "Unsaved text for `file`, checked in memory instead of the file on disk."}


@dataclass
class Tool:
    name: str
    title: str
    description: str
    properties: dict
    run: object
    required: tuple[str, ...] = ()

    def input_schema(self) -> dict:
        out = {"type": "object", "properties": self.properties, "additionalProperties": False}
        if self.required:
            out["required"] = list(self.required)
        return out


TOOLS = [
    Tool(
        "list_projects",
        "List schema projects",
        "The schema projects this server reads (QuickDBD .txt, DBML .dbml, dbt manifests): their files, table and "
        "relationship counts, errors. Call first when you don't know which project to use.",
        {},
        list_projects,
    ),
    Tool(
        "list_tables",
        "List tables",
        "Every table (or those matching `select`) with aliases, column count and the first line of its doc, "
        "grouped by file / dbt folder / TableGroup.",
        {"select": SELECT, "project": PROJECT},
        list_tables,
    ),
    Tool(
        "describe_tables",
        "Describe tables",
        "Columns (type, PK, FK target, null, default, docs), the relationships each table takes part in with "
        "cardinality, and where it is defined. Up to 25 tables.",
        {
            "tables": {
                "type": "array",
                "items": {"type": "string", "maxLength": MAX_ARG},
                "maxItems": 25,
                "description": "Table names or aliases (case-insensitive).",
            },
            "select": SELECT,
            "project": PROJECT,
        },
        describe_tables,
    ),
    Tool(
        "search_schema",
        "Search the schema",
        "Find tables, columns and docs whose text contains `query` (case-insensitive; `*` and `?` work as wildcards). "
        "Use it to find where a concept lives, e.g. 'email' or 'customer_id'.",
        {"query": {"type": "string", "maxLength": MAX_ARG}, "project": PROJECT},
        search_schema,
        ("query",),
    ),
    Tool(
        "join_path",
        "Join path and SQL",
        "The shortest chain of relationships between two tables and a SQL FROM/JOIN clause for it, with notes on "
        "optional (LEFT JOIN) and row-multiplying joins, and other relationships between the same tables.",
        {
            "from": {"type": "string", "maxLength": MAX_ARG, "description": "Start table."},
            "to": {"type": "string", "maxLength": MAX_ARG, "description": "End table."},
            "project": PROJECT,
        },
        join_path,
        ("from", "to"),
    ),
    Tool(
        "check_schema",
        "Check schema files",
        "Validate the project's schema files (after editing them, or `content` before saving). Reports "
        "path:line: severity: message. Names in messages may have non-alphanumeric characters as character codes: "
        "dbo46Order32Line is dbo.Order Line.",
        {
            "strict": {"type": "boolean", "description": "Count warnings (QuickDBD incompatibilities) as failures."},
            "file": FILE,
            "content": CONTENT,
            "project": PROJECT,
        },
        check_schema,
    ),
    Tool(
        "diff_schema",
        "Diff against git",
        "Tables, columns and relationships added, removed or changed since a git ref. For a branch review pass "
        "base='main' (compared from where the branch left it).",
        {
            "base": {"type": "string", "maxLength": 200, "description": "Git ref (default HEAD: uncommitted changes)."},
            "merge_base": {
                "type": "boolean",
                "description": "Compare with the commit where HEAD branched off `base` (default: true unless base is "
                "HEAD).",
            },
            "format": {"type": "string", "enum": ["text", "markdown"], "description": "markdown suits a PR comment."},
            "file": FILE,
            "content": CONTENT,
            "project": PROJECT,
        },
        diff_schema,
    ),
    Tool(
        "render_diagram",
        "Render a diagram",
        "A PNG of the ER diagram for some tables, to show the user or look at the shape. For facts, prefer "
        "describe_tables and join_path. Up to about 30 tables with columns, 100 with headers only.",
        {
            "select": SELECT,
            "focus": {"type": "string", "maxLength": MAX_ARG, "description": "A table to centre on."},
            "depth": {"type": "integer", "minimum": 0, "maximum": 5, "description": "Hops around `focus` (default 1)."},
            "mode": {"type": "string", "enum": ["full", "keys", "header"], "description": "Columns shown."},
            "project": PROJECT,
        },
        render_diagram,
    ),
    Tool(
        "syntax_reference",
        "Schema syntax reference",
        "How to write QuickDBD (.txt) or DBML schema text for qdbd. Read it before editing schema files.",
        {"syntax": {"type": "string", "enum": ["quickdbd", "dbml"]}},
        syntax_reference,
    ),
]

INSTRUCTIONS = """qdbd reads this project's database schema (QuickDBD .txt, DBML .dbml or a dbt manifest) and answers \
from the compiled model: resolved tables, keys, relationships with cardinality, docs.
- Explore: list_tables or search_schema, then describe_tables for columns and keys.
- Write SQL: join_path gives the join chain and a FROM/JOIN clause; heed its notes on LEFT JOINs and row \
multiplication.
- Edit schema files: read syntax_reference first; after editing (or before saving, with `content`) run check_schema.
- Review changes: diff_schema with base='main' for a branch, or the default HEAD for uncommitted edits.
- render_diagram returns a PNG for the user.
- Several projects: list_projects, then pass `project`.
Selectors: name globs (fct_*), +name (and what it references), name+ (and what references it), group:, file:, col:, \
tag:; space = union, comma = intersection, ! = exclude."""
