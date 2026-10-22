"""`qdbd convert`: QuickDBD text <-> DBML.

Each input file becomes one output file (or, DBML -> QuickDBD with ``split_groups``, one file per TableGroup, since
QuickDBD groups tables by file). Whatever the target can't express is reported as a warning and recorded in
``ConvertResult.lost``; ``canonical`` leaves those out, so the caller's self-check (recompile the output, compare)
holds for everything else.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .dbml import REL_OPS
from .model import REL_TYPES, Column, Diagnostic, Relationship, Schema, Table
from .parser import FileParse, compile_files

SUFFIX = {"dbml": ".dbml", "quickdbd": ".txt"}
_QDBD_OP = {cards: op for op, cards in REL_TYPES.items()}
_DBML_OP = {cards: op for op, cards in REL_OPS.items()}
_PLAIN_DBML = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PLAIN_QDBD = re.compile(r"[A-Za-z0-9_]+")
_ARG = r"([+-]*\d+(\.\d+)?|[A-Za-z_]\w*)"  # what dbdiagram.io takes inside a type's parentheses
_DBML_TYPE = re.compile(rf"[A-Za-z_]\w*(\.[A-Za-z_]\w*)?(\({_ARG}(,{_ARG})*\))?(\[\d*\])*")
_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_EXPRESSION = re.compile(r"[A-Z][A-Z0-9_]*|.*\(.*\).*")  # CURRENT_TIMESTAMP, now(), GETUTCDATE()


@dataclass
class ConvertResult:
    files: dict[str, str] = field(default_factory=dict)  # output path (relative) -> text
    warnings: list[Diagnostic] = field(default_factory=list)
    lost: set[tuple] = field(default_factory=set)  # canonical keys the target can't hold
    layout: dict[str, tuple[float, float]] = field(default_factory=dict)  # QuickDBD [layout], by table name


def convert(sources: list[tuple[str, str, str]], to: str, split_groups: bool) -> ConvertResult:
    """``sources``: ``(display path, output-relative path, text)``. Files already in ``to`` are copied as is."""
    schema, parses = compile_files([(d, t) for d, _, t in sources])
    res = ConvertResult()
    for t in schema.tables.values():
        if t.id in schema.layout:
            res.layout[t.name] = schema.layout[t.id]
    outs = [str(PurePosixPath(rel).with_suffix(SUFFIX[to])) for _, rel, _ in sources]
    copied = {fp.path for fp in parses if fp.syntax == to}
    taken = {out for out, fp in zip(outs, parses, strict=True) if fp.path in copied}
    fks = _plan_foreign_keys(schema, {fp.path for fp in parses} - copied, res) if to == "quickdbd" else {}
    for (_, _, text), fp, out in zip(sources, parses, outs, strict=True):
        if fp.path in copied:
            res.files[out] = text
            continue
        if to == "dbml":
            files = _DbmlWriter(schema, fp, res).write(out)
        else:
            files = _QuickdbdWriter(schema, fp, res, split_groups, fks, taken).write(out)
        res.files.update(files)
    return res


# --------------------------------------------------------------------------- canonical form (the self-check)


def _norm_default(value: str | None) -> str | None:
    if value is None:
        return None
    return value.lower() if value.lower() in ("true", "false", "null") else value


def _doc(lines: list[str]) -> list[str]:
    return [x.strip() for x in lines if x.strip()]


def canonical(schema: Schema, lost: set[tuple]) -> dict:
    """Tables, columns and relationships by name, minus the ``lost`` keys."""
    tables: dict = {}
    for t in schema.tables.values():
        cols = {}
        for c in t.columns.values():
            if c.virtual:
                continue
            col = {
                "type": c.type or "", "pk": c.pk, "unique": c.unique, "index": c.index, "nullable": c.nullable,
                "identity": c.identity, "default": _norm_default(c.default), "doc": _doc(c.comments),
            }  # fmt: skip
            for k in list(col):
                if ("col", t.name, c.name, k) in lost:
                    del col[k]
            cols[c.name] = col
        table = {"cols": cols, "doc": _doc(t.comments), "aliases": t.aliases, "tags": t.tags, "dbt_tags": t.dbt_tags}
        for k in list(table):
            if ("table", t.name, k) in lost:
                del table[k]
        tables[t.name] = table
    rels = {}
    for r in schema.valid_relationships():
        key, cards = _rel_key(schema, r)
        if ("rel", *key) not in lost:
            rels[key] = cards
    return {"tables": tables, "rels": rels}


def _end(schema: Schema, e) -> tuple[str, str | None]:
    t = schema.tables[e.table]
    c = t.columns[e.column]
    return t.name, None if c.virtual else c.name


def _rel_key(schema: Schema, r: Relationship) -> tuple[tuple, tuple]:
    a, b = _end(schema, r.a), _end(schema, r.b)
    if (a[0], a[1] or "") <= (b[0], b[1] or ""):
        return (a, b), (r.a.card, r.b.card)
    return (b, a), (r.b.card, r.a.card)


# --------------------------------------------------------------------------- DBML output


def _dbml_name(name: str) -> str:
    if _PLAIN_DBML.fullmatch(name):
        return name
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dbml_string(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


def _dbml_default(value: str) -> str:
    if _NUMBER.fullmatch(value) or value.lower() in ("true", "false", "null"):
        return value
    if _EXPRESSION.fullmatch(value) and "`" not in value:
        return f"`{value}`"
    return _dbml_string(value)


class _DbmlWriter:
    def __init__(self, schema: Schema, fp: FileParse, res: ConvertResult):
        self.schema, self.fp, self.res = schema, fp, res

    def warn(self, line: int, msg: str) -> None:
        self.res.warnings.append(Diagnostic(self.fp.path, line, msg, "warning"))

    def write(self, out: str) -> dict[str, str]:
        fp, lines = self.fp, []
        lines += [f"// {c}" for c in fp.general_comments]
        if lines:
            lines.append("")
        for k in ("zoom", "position"):
            if fp.settings.get(k) is not None:
                line = fp.settings.get("_lines", {}).get(k, 1)
                self.warn(line, f"settings: [settings] {k.capitalize()} has no DBML equivalent; dropped")
        for tag, (color, _) in sorted(fp.colors.items()):
            lines.append(f"// @color {tag} {color}")
        if fp.colors:
            lines.append("")
        for t in (t for t in self.schema.tables.values() if t.path == fp.path):
            lines += self.table(t)
            lines.append("")
        for r in (r for r in self.schema.relationships if r.path == fp.path):
            ref = self.ref(r)
            if ref:
                lines.append(ref)
        return {out: "\n".join(lines).rstrip("\n") + "\n"}

    def table(self, t: Table) -> list[str]:
        out = []
        if t.tags:
            out.append(f"// @tag: {', '.join(t.tags)}")
        if t.dbt_tags:
            out.append(f"// @dbt-tags: {', '.join(t.dbt_tags)}")
        head = f"Table {_dbml_name(t.name)}"
        if t.aliases:
            head += f" as {_dbml_name(t.aliases[0])}"
            if len(t.aliases) > 1:
                self.warn(t.line, f"alias: DBML takes one alias; dropped {', '.join(t.aliases[1:])}")
                self.res.lost.add(("table", t.name, "aliases"))
        out.append(head + " {")
        indexed = []
        for c in t.columns.values():
            if c.virtual:
                continue
            settings = []
            if c.pk:
                settings.append("pk")
            if c.identity:
                settings.append("increment")
            if c.nullable:
                settings.append("null")
            if c.unique:
                settings.append("unique")
            if c.default is not None:
                settings.append(f"default: {_dbml_default(c.default)}")
            if c.comments:
                settings.append(f"note: {_dbml_string(chr(10).join(c.comments))}")
            if c.index:
                indexed.append(c.name)
            typ = c.type or ""
            if not typ:
                self.warn(c.line, f"type: column '{c.name}' has no type, which DBML requires; wrote 'unknown'")
                self.res.lost.add(("col", t.name, c.name, "type"))
                typ = "unknown"
            typ = typ if _DBML_TYPE.fullmatch(typ) else _dbml_name(typ)
            out.append(f"  {_dbml_name(c.name)} {typ}" + (f" [{', '.join(settings)}]" if settings else ""))
        if indexed:
            out += ["", "  indexes {"] + [f"    {_dbml_name(n)}" for n in indexed] + ["  }"]
        if t.comments:
            lines = [x.replace("\\", "\\\\").replace("'''", "\\'''") for x in t.comments]
            out += ["", "  Note: '''"] + [f"    {x}".rstrip() for x in lines] + ["  '''"]
        out.append("}")
        return out

    def ref(self, r: Relationship) -> str | None:
        a, b = _end(self.schema, r.a), _end(self.schema, r.b)
        if a[1] is None or b[1] is None:
            key, _ = _rel_key(self.schema, r)
            self.res.lost.add(("rel", *key))
            self.warn(r.line, f"table-level relationship: {a[0]} - {b[0]} has no DBML form; kept as a comment")
            return f"// rel: {a[0]} {_QDBD_OP.get((r.a.card, r.b.card), '-')} {b[0]}"
        op = _DBML_OP[(r.a.card, r.b.card)]
        return f"Ref: {_dbml_name(a[0])}.{_dbml_name(a[1])} {op} {_dbml_name(b[0])}.{_dbml_name(b[1])}"


# --------------------------------------------------------------------------- QuickDBD output


def _qdbd_name(name: str) -> str:
    return name if _PLAIN_QDBD.fullmatch(name) else f'"{name}"'


def _quickdbd_column(col: Column, fks: list[str]) -> str:
    parts = [_qdbd_name(col.name)]
    if col.pk:
        parts.append("PK")
    typ = col.type or ""
    parts.append(_qdbd_name(typ) if " " in typ or "#" in typ else typ)
    if col.nullable:
        parts.append("NULL")
    if col.unique and not col.pk:
        parts.append("UNIQUE")
    if col.index and not (col.pk or col.unique):
        parts.append("INDEX")
    if col.identity:
        parts.append("IDENTITY")
    if col.default is not None:
        d = col.default
        parts.append(f'default="{d}"' if re.search(r"[\s#]", d) else f"default={d}")
    parts += fks
    return " ".join(p for p in parts if p)


def _plan_foreign_keys(schema: Schema, written: set[str], res: ConvertResult) -> dict[tuple[str, str], list[str]]:
    """`FK op table.column` clauses per (table id, column id), for the relationships declared in the files being
    written. A clause goes on a column of a table that's being written, the non-key end when it can."""
    out: dict[tuple[str, str], list[str]] = {}
    valid = {id(r) for r in schema.valid_relationships()}

    def warn(r: Relationship, msg: str) -> None:
        res.warnings.append(Diagnostic(r.path, r.line, msg, "warning"))

    for r in schema.relationships:
        if r.path not in written or id(r) not in valid:
            continue
        ends = [(r.a, r.b), (r.b, r.a)]
        if schema.tables[r.a.table].columns[r.a.column].pk and not schema.tables[r.b.table].columns[r.b.column].pk:
            ends.reverse()
        ends = [e for e in ends if schema.tables[e[0].table].path in written]
        key, _ = _rel_key(schema, r)
        if not ends:
            res.lost.add(("rel", *key))
            warn(r, "relationship: both tables are in files kept as they are; add it to one of them by hand")
            continue
        chosen = next(((h, t, _QDBD_OP[(h.card, t.card)]) for h, t in ends if (h.card, t.card) in _QDBD_OP), None)
        if chosen is None:
            here, there = ends[0]
            chosen = (here, there, _QDBD_OP[(_required(here.card), _required(there.card))])
            res.lost.add(("rel", *key))
            warn(r, "relationship: QuickDBD has no operator for these cardinalities; made both sides required")
        here, there, op = chosen
        t = schema.tables[there.table]
        target = f"{_qdbd_name(t.name)}.{_qdbd_name(t.columns[there.column].name)}"
        out.setdefault((here.table, here.column), []).append(f"FK {op} {target}")
    return out


class _QuickdbdWriter:
    def __init__(
        self,
        schema: Schema,
        fp: FileParse,
        res: ConvertResult,
        split_groups: bool,
        fks: dict[tuple[str, str], list[str]],
        taken: set[str],
    ):
        self.schema, self.fp, self.res, self.split = schema, fp, res, split_groups
        self.fks, self.taken = fks, taken  # FK clauses for every file; output names already used

    def warn(self, line: int, msg: str) -> None:
        self.res.warnings.append(Diagnostic(self.fp.path, line, msg, "warning"))

    def write(self, out: str) -> dict[str, str]:
        fp = self.fp
        tables = [t for t in self.schema.tables.values() if t.path == fp.path]
        for line, what in fp.unmodelled:
            self.warn(line, f"{what}: no QuickDBD equivalent; dropped")
        header = [f"# {c}" for c in fp.general_comments]
        if header:
            header.append("")
        for name, values in fp.enums.items():
            header.append(f"# enum {name}: {', '.join(values)}")
        for tag, (color, _) in sorted(fp.colors.items()):
            header.append(f"# @color {tag} {color}")
        if not self.split:
            for group, line in fp.groups.items():
                self.warn(line, f"TableGroup {group}: QuickDBD groups tables by file (use -o DIR to split); dropped")
        groups: dict[str, list[Table]] = {}
        for t in tables:
            groups.setdefault(t.group if (t.group and self.split) else "", []).append(t)
        if not groups:
            groups[""] = []
        files = {}
        for group, members in groups.items():
            wanted = str(PurePosixPath(out).with_name(re.sub(r"[^\w.-]+", "_", group) + ".txt")) if group else out
            name, n = wanted, 1
            while name in self.taken:
                n += 1
                name = str(PurePosixPath(wanted).with_name(f"{PurePosixPath(wanted).stem}-{n}.txt"))
            if name != wanted:
                self.warn(fp.groups.get(group, 1), f"TableGroup {group}: {wanted} is taken; wrote {name}")
            self.taken.add(name)
            body = (header + [""] if not files else []) + [line for t in members for line in [*self.table(t), ""]]
            files[name] = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).rstrip("\n") + "\n"
        return files

    def table(self, t: Table) -> list[str]:
        out = []
        if t.color:
            self.warn(t.line, f"headercolor: QuickDBD has no table colour; dropped {t.color}")
        if any("#" in x for x in t.comments):
            self.warn(t.line, f"note: QuickDBD ends a comment at '#', so the note of {t.name} is cut there")
            self.res.lost.add(("table", t.name, "doc"))
        out += [f"# {x}" for x in t.comments if x.strip()]
        if t.tags:
            out.append(f"# @tag: {', '.join(t.tags)}")
        if t.dbt_tags:
            out.append(f"# @dbt-tags: {', '.join(t.dbt_tags)}")
        out.append(_qdbd_name(t.name) + (f" as {', '.join(t.aliases)}" if t.aliases else ""))
        out.append("-")
        for c in t.columns.values():
            if c.virtual:
                continue
            if c.pk and c.unique:
                self.warn(c.line, f"unique: '{c.name}' is a primary key, which QuickDBD treats as unique already")
                self.res.lost.add(("col", t.name, c.name, "unique"))
            if c.index and (c.pk or c.unique):
                self.warn(c.line, f"index: '{c.name}' is a key, which QuickDBD treats as indexed already")
                self.res.lost.add(("col", t.name, c.name, "index"))
            if any("#" in x for x in c.comments):
                self.warn(
                    c.line, f"note: QuickDBD ends a comment at '#', so the note of {t.name}.{c.name} is cut there"
                )
                self.res.lost.add(("col", t.name, c.name, "doc"))
            if c.default is not None and '"' in c.default:
                self.warn(c.line, f"default: QuickDBD can't hold a '\"' in a default; dropped {t.name}.{c.name}'s")
                self.res.lost.add(("col", t.name, c.name, "default"))
                c = dataclasses.replace(c, default=None)
            out += [f"# {x}" for x in c.comments if x.strip()]
            out.append(_quickdbd_column(c, self.fks.get((t.id, c.id), [])))
        return out


def _required(card: str) -> str:
    return {"zeroOne": "one", "zeroMany": "many"}.get(card, card)
