"""`qdbd diff`: compare two versions of a schema (two paths, or a git ref vs the working tree).

Tables match by name, columns by name within a table, relationships by their two endpoints
(normalised child -> parent). The result can be printed (text / markdown / json) or attached to
the diagram model so the page colours what changed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .model import VIRTUAL_FIELD, Column, Relationship, Schema
from .parser import compile_sources

COL_FIELDS = ("type", "pk", "fk", "nullable", "unique", "index", "identity", "default")


class DiffError(Exception):
    pass


@dataclass
class TableChange:
    name: str
    added_cols: list[str] = field(default_factory=list)
    removed_cols: list[str] = field(default_factory=list)
    changed_cols: dict[str, list[str]] = field(default_factory=dict)  # col -> ["type: int -> bigint", ...]

    @property
    def empty(self) -> bool:
        return not (self.added_cols or self.removed_cols or self.changed_cols)


@dataclass
class SchemaDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[TableChange] = field(default_factory=list)
    rels_added: list[str] = field(default_factory=list)
    rels_removed: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.rels_added or self.rels_removed)

    def to_json(self) -> dict:
        return {
            "tables_added": self.added,
            "tables_removed": self.removed,
            "tables_changed": [
                {
                    "table": c.name,
                    "columns_added": c.added_cols,
                    "columns_removed": c.removed_cols,
                    "columns_changed": c.changed_cols,
                }
                for c in self.changed
            ],
            "relationships_added": self.rels_added,
            "relationships_removed": self.rels_removed,
        }


def _col_desc(c: Column, field_name: str) -> str:
    v = getattr(c, field_name)
    if isinstance(v, bool):
        return "yes" if v else "no"
    return "none" if v in (None, "") else str(v)


def _rel_key(s: Schema, r: Relationship) -> str:
    def end(e):
        t = s.tables[e.table]
        col = t.columns.get(e.column)
        return t.name if (col is None or col.virtual or e.column == VIRTUAL_FIELD) else f"{t.name}.{col.name}"

    many = ("many", "zeroMany")
    a_child = r.a.card in many or r.b.card not in many
    child, parent = (r.a, r.b) if a_child else (r.b, r.a)
    card = {"one": "1", "many": "N", "zeroOne": "0..1", "zeroMany": "0..N"}
    return f"{end(child)} -> {end(parent)} ({card[child.card]}:{card[parent.card]})"


def diff_schemas(old: Schema, new: Schema) -> SchemaDiff:
    d = SchemaDiff()
    old_t = {t.name: t for t in old.tables.values()}
    new_t = {t.name: t for t in new.tables.values()}
    d.added = [n for n in new_t if n not in old_t]
    d.removed = [n for n in old_t if n not in new_t]
    for name, nt in new_t.items():
        ot = old_t.get(name)
        if ot is None:
            continue
        ch = TableChange(name)
        oc = {c.name: c for c in ot.columns.values() if not c.virtual}
        nc = {c.name: c for c in nt.columns.values() if not c.virtual}
        ch.added_cols = [n for n in nc if n not in oc]
        ch.removed_cols = [n for n in oc if n not in nc]
        for cname, c in nc.items():
            if cname not in oc:
                continue
            diffs = [
                f"{f}: {_col_desc(oc[cname], f)} -> {_col_desc(c, f)}"
                for f in COL_FIELDS
                if getattr(oc[cname], f) != getattr(c, f)
            ]
            if diffs:
                ch.changed_cols[cname] = diffs
        if not ch.empty:
            d.changed.append(ch)
    ok = {_rel_key(old, r) for r in old.valid_relationships()}
    nk = {_rel_key(new, r) for r in new.valid_relationships()}
    d.rels_added = sorted(nk - ok)
    d.rels_removed = sorted(ok - nk)
    return d


# --------------------------------------------------------------------------- reading a git ref


def _git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise DiffError("git is not installed") from None
    if r.returncode != 0:
        raise DiffError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout


def sources_at_ref(ref: str, inputs: list[Path]) -> list[tuple[str, str]]:
    """The .txt and .dbml schema files under ``inputs`` as they were at git ``ref``."""
    first = inputs[0].resolve()
    root = Path(_git(["rev-parse", "--show-toplevel"], first if first.is_dir() else first.parent).strip())
    _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root)
    out: list[tuple[str, str]] = []
    seen = set()
    for p in inputs:
        rel = p.resolve().relative_to(root).as_posix()
        listed = _git(["ls-tree", "-r", "--name-only", ref, "--", rel], root).splitlines()
        for f in sorted(listed):
            if f in seen or not (f == rel or f.endswith((".txt", ".dbml"))):
                continue
            seen.add(f)
            out.append((f, _git(["show", f"{ref}:{f}"], root)))
    return out


def schema_at_ref(ref: str, inputs: list[Path]) -> Schema:
    return compile_sources(sources_at_ref(ref, inputs))


# --------------------------------------------------------------------------- output


def format_text(d: SchemaDiff, old_label: str, new_label: str) -> str:
    if d.empty:
        return f"No schema changes between {old_label} and {new_label}."
    lines = [f"Schema changes {old_label} -> {new_label}:"]
    for n in d.added:
        lines.append(f"  + table {n}")
    for n in d.removed:
        lines.append(f"  - table {n}")
    for c in d.changed:
        lines.append(f"  ~ table {c.name}")
        lines += [f"      + {x}" for x in c.added_cols]
        lines += [f"      - {x}" for x in c.removed_cols]
        for col, what in c.changed_cols.items():
            lines.append(f"      ~ {col}: {'; '.join(what)}")
    for r in d.rels_added:
        lines.append(f"  + relationship {r}")
    for r in d.rels_removed:
        lines.append(f"  - relationship {r}")
    lines.append(summary(d))
    return "\n".join(lines)


def summary(d: SchemaDiff) -> str:
    return (
        f"{len(d.added)} table(s) added, {len(d.removed)} removed, {len(d.changed)} changed; "
        f"{len(d.rels_added)} relationship(s) added, {len(d.rels_removed)} removed"
    )


def format_markdown(d: SchemaDiff, old_label: str, new_label: str) -> str:
    title = f"### Schema changes: `{old_label}` → `{new_label}`"
    if d.empty:
        return f"{title}\n\nNo schema changes."
    out = [title, "", f"**{summary(d)}**", ""]
    if d.added:
        out += ["#### ➕ Tables added", ""] + [f"- `{n}`" for n in d.added] + [""]
    if d.removed:
        out += ["#### ➖ Tables removed", ""] + [f"- `{n}`" for n in d.removed] + [""]
    if d.changed:
        out += ["#### ✏️ Tables changed", "", "| Table | Change |", "|---|---|"]
        for c in d.changed:
            rows = [f"➕ `{x}`" for x in c.added_cols] + [f"➖ `{x}`" for x in c.removed_cols]
            rows += [f"✏️ `{col}`: {'; '.join(w)}" for col, w in c.changed_cols.items()]
            for i, r in enumerate(rows):
                out.append(f"| {'`' + c.name + '`' if i == 0 else ''} | {r} |")
        out.append("")
    if d.rels_added or d.rels_removed:
        out += ["#### 🔗 Relationships", ""]
        out += [f"- ➕ `{r}`" for r in d.rels_added] + [f"- ➖ `{r}`" for r in d.rels_removed] + [""]
    return "\n".join(out).rstrip() + "\n"


def format_json(d: SchemaDiff) -> str:
    return json.dumps(d.to_json(), indent=2)


# --------------------------------------------------------------------------- annotate the diagram model


def annotate_model(model: dict, d: SchemaDiff, base_label: str) -> dict:
    """Add ``diff`` markers so render.js colours added/changed tables and columns."""
    added = set(d.added)
    changed = {c.name: c for c in d.changed}
    for t in model["tables"]:
        if t["name"] in added:
            t["diff"] = {"state": "added"}
        elif t["name"] in changed:
            c = changed[t["name"]]
            cols = {}
            for col in t["cols"]:
                if col["name"] in c.added_cols:
                    cols[col["id"]] = "added"
                elif col["name"] in c.changed_cols:
                    cols[col["id"]] = "changed"
            t["diff"] = {
                "state": "changed",
                "cols": cols,
                "removedCols": c.removed_cols,
                "changes": {k: v for k, v in c.changed_cols.items()},
            }
    model["diff"] = {
        "base": base_label,
        "added": len(d.added),
        "changed": len(d.changed),
        "removed": d.removed,
        "relsAdded": d.rels_added,
        "relsRemoved": d.rels_removed,
    }
    return model
