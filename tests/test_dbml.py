"""DBML parser: the reference corpus from @dbml/parse 10.3.1 (tests/fixtures/dbml-ref) plus qdbd's own cases."""

import json
from pathlib import Path

import pytest

from quickdbd_cli.dbml import parse_dbml
from quickdbd_cli.parser import _Resolver

REF = Path(__file__).parent / "fixtures" / "dbml-ref"
CARD = {"1": "one", "*": "many", "0..1": "zeroOne", "0..*": "zeroMany"}
OPS = {">": ("*", "1"), "<": ("1", "*"), "-": ("1", "1"), "<>": ("*", "*")}
# Cases where the parse-stage snapshot is clean but @dbml/core (which dbdiagram.io runs on top) rejects the file.
CORE_REJECTS = {
    "interpreter/tablepartial_causing_circular_ref": "partial's inline refs: one self-ref, one duplicating T's own",
}


def compile_dbml(text: str, path: str = "main.dbml"):
    fp = parse_dbml(text, path)
    return fp, _Resolver([fp]).run()


def errors(schema):
    return [d for d in schema.diagnostics if d.severity == "error"]


def _cases(clean: bool):
    out = []
    for f in sorted(REF.glob("*/*.json")):
        exp = json.loads(f.read_text())
        if bool(exp["errors"]) != clean:
            out.append(pytest.param(f.with_suffix(".dbml"), exp, id=f"{f.parent.name}/{f.stem}"))
    return out


def _display(name: str, schema: str | None) -> str:
    return name if schema in (None, "public") else f"{schema}.{name}"


def _merged_fields(table: dict, partials: dict) -> list[dict]:
    """Table fields with partials injected the way @dbml/core does: local wins, then the last partial."""
    fields: list = list(table["fields"])
    names = {f["name"] for f in fields}
    ordered = sorted(table["partials"], key=lambda p: p["order"], reverse=True)
    for p in reversed(ordered):
        fields.insert(p["order"], None)
    for p in ordered:
        new = [f for f in partials[p["name"]]["fields"] if f["name"] not in names]
        names |= {f["name"] for f in new}
        fields[p["order"] : p["order"] + 1] = new
    return fields


def _expected(db: dict):
    partials = {p["name"]: p for p in db["tablePartials"]}
    tables, rels = {}, set()

    def rel(e0, e1):
        for c0, c1 in zip(e0["fields"], e1["fields"], strict=True):
            a = (_display(e0["table"], e0.get("schema")), c0, CARD[e0["relation"]])
            b = (_display(e1["table"], e1.get("schema")), c1, CARD[e1["relation"]])
            rels.add(tuple(sorted((a, b))))

    for t in db["tables"]:
        name = _display(t["name"], t["schema"])
        fields = _merged_fields(t, partials)
        cols = {}
        for f in fields:
            typ = f"{f['type_schema']}.{f['type']}" if f.get("type_schema") else f["type"]
            cols[f["name"]] = {
                "type": typ,
                "pk": f.get("pk", False),
                "unique": f.get("unique", False),
                "nullable": f.get("not_null") is False,
                "identity": f.get("increment", False),
            }
        injected = {f["name"] for f in fields} - {f["name"] for f in t["fields"]}
        for f in fields:  # a table's own inline refs are in db.refs; those of injected partial fields aren't
            for r in f.get("inline_refs", []) if f["name"] in injected else []:
                left, right = OPS[r["relation"]]
                rel(
                    {"table": t["name"], "schema": t["schema"], "fields": [f["name"]], "relation": left},
                    {**r, "relation": right, "table": r["table"] or t["name"]},
                )
        indexes = list(t["indexes"]) + [i for p in t["partials"] for i in partials[p["name"]]["indexes"]]
        for i in indexes:
            if i["pk"]:
                for c in i["columns"]:
                    cols[c]["pk"] = True
            elif i["unique"] and len(i["columns"]) == 1 and not i["expressions"]:
                cols[i["columns"][0]]["unique"] = True
        tables[name] = cols
    for r in db["refs"]:
        rel(*r["endpoints"])
    groups = {_display(x["name"], x.get("schema")): g["name"] for g in db["tableGroups"] for x in g["tables"]}
    return tables, rels, groups


def _actual(schema):
    tables = {}
    for t in schema.tables.values():
        tables[t.name] = {
            c.name: {"type": c.type, "pk": c.pk, "unique": c.unique, "nullable": c.nullable, "identity": c.identity}
            for c in t.columns.values()
            if not c.virtual
        }
    rels = set()
    for r in schema.valid_relationships():
        ends = []
        for e in (r.a, r.b):
            t = schema.tables[e.table]
            ends.append((t.name, t.columns[e.column].name, e.card))
        rels.add(tuple(sorted(ends)))
    groups = {t.name: t.group for t in schema.tables.values() if t.group}
    return tables, rels, groups


@pytest.mark.parametrize(("path", "exp"), _cases(clean=True))
def test_reference_accepts(path, exp, request):
    _, schema = compile_dbml(path.read_text(encoding="utf-8"))
    case = request.node.callspec.id
    if case in CORE_REJECTS:
        assert errors(schema), CORE_REJECTS[case]
        return
    assert [d.format() for d in errors(schema)] == []
    tables, rels, groups = _expected(exp["database"])
    a_tables, a_rels, a_groups = _actual(schema)
    assert a_tables == tables
    assert a_rels == rels
    assert a_groups == groups


@pytest.mark.parametrize(("path", "exp"), _cases(clean=False))
def test_reference_rejects(path, exp):
    _, schema = compile_dbml(path.read_text(encoding="utf-8"))
    ours = {d.line for d in errors(schema)}
    assert ours, "accepted a file the reference parser rejects"
    if path.parent.name == "parser":
        return  # parser-stage cases wrap syntax in made-up `Test` elements, which qdbd rejects at their first line
    theirs = {e["line"] for e in exp["errors"]}
    assert ours & theirs, f"error lines {sorted(ours)}, reference {sorted(theirs)}"


TEAM = (Path(__file__).parent / "fixtures" / "dbml" / "team.dbml").read_text()


def test_teammate_style():
    _, schema = compile_dbml(TEAM)
    assert errors(schema) == []
    assert len(schema.tables) == 10
    _, rels, _ = _actual(schema)
    one_to_one = {r for r in rels if r[0][2] == r[1][2] == "one"}
    assert one_to_one == {
        (("visits", c, "one"), ("visits_trend", c, "one")) for c in ("guest_sk", "period_code", "as_of")
    }
    assert len(rels) == 10
    pk = schema.tables["guests"].columns["guest_sk"]
    assert pk.pk and pk.type == "integer"
    assert schema.tables["visits"].columns["guest_sk"].fk


def test_crlf_tabs_bom_no_trailing_newline():
    variant = "﻿" + TEAM.replace("  ", "\t").replace("\n", "\r\n").rstrip()
    _, a = compile_dbml(TEAM)
    _, b = compile_dbml(variant)
    assert errors(b) == []
    assert _actual(a) == _actual(b)


def test_quoted_names_with_spaces_and_schema():
    text = """
Table "core"."order items" {
  "line no" int [pk]
}
Table x {
  y int
}
Ref: x.y > "core"."order items"."line no"
"""
    _, schema = compile_dbml(text)
    assert errors(schema) == []
    assert {t.name for t in schema.tables.values()} == {"core.order items", "x"}
    _, rels, _ = _actual(schema)
    assert rels == {(("core.order items", "line no", "one"), ("x", "y", "many"))}


def test_public_schema_is_the_default():
    text = "Table public.users {\n  id int [pk]\n}\nTable posts {\n  user_id int [ref: > users.id]\n}\n"
    _, schema = compile_dbml(text)
    assert errors(schema) == []
    assert {t.name for t in schema.tables.values()} == {"users", "posts"}
    assert len(schema.valid_relationships()) == 1


def test_partial_result_on_error():
    text = "Table a {\n  id int [pk]\n}\nTable b {\n  id int [pk,\n  name varchar\n}\nTable c {\n  id int\n}\n"
    _, schema = compile_dbml(text)
    assert [d.line for d in errors(schema)][:1] == [5]
    assert {t.name for t in schema.tables.values()} >= {"a", "c"}


def test_use_warns_and_renamed_import_errors():
    _, schema = compile_dbml("use * from './base'\nTable a {\n  id int\n}\n")
    assert errors(schema) == []
    assert any("ignores `use`" in d.message for d in schema.warnings)
    _, schema = compile_dbml("use { table users as people } from './base'\nTable a {\n  id int\n}\n")
    assert [d.line for d in errors(schema)] == [1]


def test_unmodelled_recorded():
    text = """\
Enum status {
  active
  gone
}
Table a {
  id int [pk]
  s status
  checks {
    `id > 0`
  }
}
Records a(id) {
  1
}
Table b {
  id int
}
Dep: a -> b
"""
    fp, schema = compile_dbml(text)
    assert errors(schema) == []
    lines = {line for line, _ in fp.unmodelled}
    assert {1, 8, 12, 18} <= lines  # enum, checks block, records, Dep
    assert fp.enums == {"status": ["active", "gone"]}


def test_notes_become_docs():
    text = """\
Table a [note: 'table note'] {
  id int [pk, note: 'the id']
  Note: '''
    first line
      indented
  '''
}
"""
    _, schema = compile_dbml(text)
    assert errors(schema) == []
    t = schema.tables["a"]
    assert t.columns["id"].comments == ["the id"]
    assert t.comments == ["first line", "  indented"]


def test_tags_and_colors_from_comments():
    text = """\
// @color hot #ff0000
// @tag: hot, pii
Table a [headercolor: #0A0] {
  id int
}
"""
    fp, schema = compile_dbml(text)
    assert errors(schema) == []
    assert schema.tables["a"].tags == ["hot", "pii"]
    assert schema.tables["a"].color == "#00aa00"
    assert fp.colors["hot"][0] == "#ff0000"


def test_optional_relationship_operators():
    text = "Table a {\n  id int [pk]\n}\nTable b {\n  a_id int\n}\nRef: b.a_id >? a.id\n"
    _, schema = compile_dbml(text)
    assert errors(schema) == []
    (r,) = schema.valid_relationships()
    cards = {schema.tables[e.table].name: e.card for e in (r.a, r.b)}
    assert cards == {"b": "many", "a": "zeroOne"}  # `?` makes its own side optional


def test_end_line_and_alias():
    text = "Table users as U {\n  id int [pk]\n}\nTable p {\n  uid int [ref: > U.id]\n}\n"
    _, schema = compile_dbml(text)
    assert errors(schema) == []
    assert schema.tables["users"].aliases == ["U"]
    assert schema.tables["users"].end_line == 3
    assert len(schema.valid_relationships()) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Table a {\n  id int\n  indexes\n  {\n    id\n  }\n}\n",
        "Table a {\n  {\n  }\n}\n",
        "{\n}\n",
        "Table a {\n  id int\n  [pk] {\n  }\n}\n",
    ],
)
def test_headerless_blocks_are_errors_not_crashes(text):
    _, schema = compile_dbml(text)
    assert errors(schema)


@pytest.mark.parametrize(
    "text",
    [
        "Table users\n{\n  id int [pk]\n}\nTable posts\n{\n  uid int [ref: > users.id]\n}\n",
        "Table users [headercolor: #fff]\n\n{\n  id int [pk]\n}\nTable posts {\n  uid int\n}\n"
        "Ref r\n{\n  posts.uid > users.id\n}\n",
        "Table users {\n  id int [pk]\n}\nTable posts {\n  uid int\n}\nRef:\n  posts.uid > users.id\n",
        "Table users {\n  id int [pk]\n}\nTable posts {\n  uid int\n}\nRef: posts.uid >\n  users.id\n",
        "Table users {\n  id int [pk]\n}\nTable posts {\n  uid int\n}\nRef: posts.uid\n  > users.id\n",
    ],
)
def test_newlines_inside_headers_and_refs(text):
    _, schema = compile_dbml(text)
    assert [d.format() for d in errors(schema)] == []
    assert {t.name for t in schema.tables.values()} == {"users", "posts"}
    assert len(schema.valid_relationships()) == 1


def test_newline_before_brace_in_group_and_enum():
    text = "Enum s\n{\n  a\n}\nTable t {\n  x s\n}\nTableGroup g\n{\n  t\n}\n"
    fp, schema = compile_dbml(text)
    assert errors(schema) == []
    assert fp.enums == {"s": ["a"]} and schema.tables["t"].group == "g"


def test_indexes_needs_its_brace_on_the_same_line():
    _, schema = compile_dbml("Table a {\n  id int\n  indexes\n  {\n    id\n  }\n}\n")
    assert errors(schema)  # as dbdiagram.io: inside a table, `indexes` then a newline is a column


def test_unclosed_brace_keeps_later_tables():
    text = (
        "Table a {\n  id int\n}\nTable b {\n  id int\n\nTable c {\n  id int\n}\nTable d {\n  id int\n}\n"
        "Ref: d.id > c.id\n"
    )
    _, schema = compile_dbml(text)
    assert [d.line for d in errors(schema)] == [7]  # where dbdiagram.io reports it: the next table
    assert {t.name for t in schema.tables.values()} == {"a", "b", "c", "d"}
    assert len(schema.valid_relationships()) == 1


def test_missing_table_error_shows_display_name():
    text = 'Table x {\n  y int\n}\nRef: x.y > "order items"."line no"\nRef: x.y - core.users.id\n'
    _, schema = compile_dbml(text)
    msgs = [d.message for d in errors(schema)]
    assert any("'order items'" in m for m in msgs), msgs
    assert any("'core.users'" in m for m in msgs), msgs
    assert not any("32" in m or "46" in m for m in msgs), msgs


def test_crlf_multiline_note_has_no_carriage_returns():
    text = "Table a {\r\n  id int\r\n  Note: '''\r\n    hi\r\n    there\r\n  '''\r\n}\r\n"
    _, schema = compile_dbml(text)
    assert schema.tables["a"].comments == ["hi", "there"]


def test_element_name_on_the_line_after_its_keyword():
    _, schema = compile_dbml('Table\n  "users" [headercolor: #555] {\n  id int\n}\nEnum\n  status {\n  a\n}\n')
    assert errors(schema) == []
    assert [t.name for t in schema.tables.values()] == ["users"]
