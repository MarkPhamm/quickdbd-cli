"""Table tags and their header colours.

A table's tags come from the first source that has any:

1. explicit ``# @tag: dim, pii`` comments;
2. its name: ``dim_*`` / ``DimCustomer`` -> dim, ``fct_*`` -> fact, ``stg_*`` -> staging, ...;
3. ``# @dbt-tags: ...`` comments written by ``qdbd import dbt``.

The header takes the colour of the table's first tag. ``# @color TAG #hex`` overrides the defaults, and a DBML
``headercolor`` beats both.

Columns take tags too (``# @tag: added`` on or above the column line), which mark the row in the first tag's colour;
``added`` and ``removed`` default to green and red, for hand-marked proposed changes.
"""

from __future__ import annotations

from collections.abc import Iterable

from .model import Schema, Table

# tag -> name prefixes (matched as `prefix_...` or `PrefixName`)
NAME_TAGS: list[tuple[str, tuple[str, ...]]] = [
    ("dim", ("dim",)),
    ("fact", ("fct", "fact")),
    ("staging", ("stg", "staging")),
    ("intermediate", ("int",)),
    ("raw", ("raw", "src")),
]

# Table-role defaults avoid the diff colours (green = added, amber = changed) and the untagged blue; `added` and
# `removed` are meant for columns, and use the diff green on purpose.
DEFAULT_COLORS = {
    "dim": "#00838f",
    "fact": "#c2185b",
    "staging": "#546e7a",
    "intermediate": "#7b1fa2",
    "raw": "#6d4c41",
    "added": "#2e7d32",
    "removed": "#c62828",
}
PALETTE = ["#0277bd", "#4527a0", "#00695c", "#ad1457", "#827717", "#bf360c", "#37474f", "#283593", "#5d4037"]


def _name_parts(name: str) -> list[str]:
    """The name, plus the part after a source qualifier (`src.tbl`) or a dbt `<layer>_<source>__<entity>`."""
    out = [name]
    for sep in (".", "__"):
        if sep in name:
            out.append(name.rsplit(sep, 1)[1])
    return out


def name_tag(name: str) -> str | None:
    for part in _name_parts(name):
        low = part.lower()
        for tag, prefixes in NAME_TAGS:
            for p in prefixes:
                if low.startswith(p + "_") and len(low) > len(p) + 1:
                    return tag
                rest = part[len(p) :]
                if part[: len(p)] == p.capitalize() and rest[:1].isupper():
                    return tag
    return None


def table_tags(t: Table) -> list[str]:
    if t.tags:
        return list(t.tags)
    tag = name_tag(t.name)
    if tag:
        return [tag]
    return list(t.dbt_tags)


def tag_colors(schema: Schema, tag_lists: Iterable[list[str]]) -> dict[str, str]:
    """Colour of every tag in use: explicit @color, else the default, else the next palette colour (by name)."""
    used = sorted({tag for tags in tag_lists for tag in tags})
    out: dict[str, str] = {}
    i = 0
    for tag in used:
        if tag in schema.tag_colors:
            out[tag] = schema.tag_colors[tag]
        elif tag in DEFAULT_COLORS:
            out[tag] = DEFAULT_COLORS[tag]
        else:
            out[tag] = PALETTE[i % len(PALETTE)]
            i += 1
    return out


def annotate(schema: Schema, tables: list[dict]) -> list[dict]:
    """Add ``tags`` and ``color`` to each table dict of the model JSON, and ``color`` to tagged columns; return the
    legend (count = tables carrying the tag, on the table or on a column)."""
    by_id = {t["id"]: table_tags(schema.tables[t["id"]]) for t in tables}
    col_tags = {t["id"]: [g for c in t["cols"] for g in c.get("tags", [])] for t in tables}
    colors = tag_colors(schema, [*by_id.values(), *col_tags.values()])
    counts: dict[str, int] = {}
    for t in tables:
        tags = by_id[t["id"]]
        if tags:
            t["tags"] = tags
            t["color"] = colors[tags[0]]
        for c in t["cols"]:
            if c.get("tags"):
                c["color"] = colors[c["tags"][0]]
        for tag in dict.fromkeys(tags + col_tags[t["id"]]):
            counts[tag] = counts.get(tag, 0) + 1
        own = schema.tables[t["id"]].color  # DBML headercolor
        if own:
            t["color"] = own
    return [{"name": k, "color": colors[k], "count": counts[k]} for k in sorted(counts, key=lambda k: (-counts[k], k))]
