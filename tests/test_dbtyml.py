"""`# @dbt: PATH`: descriptions, tags, types and drift from a dbt project's yml (tests/fixtures/dbt-yml)."""

import json
import os
import shutil
import threading
from pathlib import Path

import pytest

from quickdbd_cli.cli import main
from quickdbd_cli.dbtyml import base_type
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_sources
from quickdbd_cli.project import Project
from quickdbd_cli.serve import make_server, poll_once

FIXTURE = Path(__file__).parent / "fixtures" / "dbt-yml"
ERD = FIXTURE / "erd"


@pytest.fixture(scope="module")
def built():
    schema = Project.open([ERD]).compile()
    model = model_json(schema)
    return schema, {t["name"]: t for t in model["tables"]}, model


def cols(table):
    return {c["name"]: c for c in table["cols"]}


def test_descriptions_come_first_then_the_schema_comment(built):
    _, tables, _ = built
    assert tables["orders"]["doc"] == "One row per order.\nThe shop's view of an order"  # doc() resolved
    assert tables["customers"]["doc"] == "One row per customer."
    assert tables["shop.raw_payments"]["doc"] == "Payments as loaded from the shop database."  # a source
    assert tables["payments"]["doc"] == "no yml, but the model exists"  # comment only
    orders = cols(tables["orders"])
    assert orders["status"]["doc"] == "placed, shipped, completed or returned."
    assert "doc" not in orders["note"]
    assert cols(tables["customers"])["name"]["doc"] == "Full name."  # same text in both: shown once


def test_types_fill_only_untyped_columns(built):
    _, tables, _ = built
    assert cols(tables["customers"])["name"]["type"] == "string"
    assert cols(tables["orders"])["status"]["type"] == "varchar(255)"  # the schema's own type wins


def test_dbt_tags_colour_headers_and_rows(built):
    _, tables, model = built
    assert tables["orders"]["tags"] == ["finance"]  # config.tags
    assert tables["customers"]["tags"] == ["crm"]  # `tags: crm`, a string
    assert cols(tables["orders"])["status"]["tags"] == ["pii"]
    assert {t["name"] for t in model["tags"]} >= {"finance", "crm", "pii"}


def test_drift_warnings_point_at_schema_lines(built):
    schema, _, _ = built
    got = [(d.line, d.message) for d in schema.diagnostics]
    assert got == [
        (5, "dbt: column 'shipped_at' (models/marts/schema.yml:19) is missing from 'orders'"),
        (9, "dbt: type 'int' differs from data_type 'numeric(10,2)' (models/marts/schema.yml:16)"),
        (10, "dbt: column 'note' is not in the yml for 'orders' (models/marts/schema.yml:4)"),
        (
            32,
            "dbt: no model, seed, snapshot or source named 'ghost' (put '# @dbt: none' above the table if it isn't "
            "one)",
        ),
    ]
    assert all(d.severity == "warning" for d in schema.diagnostics)
    assert schema.tables["planned_refunds"].dbt_skip  # opted out: no warning


def test_strict_fails_on_drift(capsys):
    assert main(["check", str(ERD)]) == 0
    assert main(["check", str(ERD), "--strict"]) == 1


def test_symbols_carry_merged_docs_and_types(capsys):
    assert main(["check", str(ERD), "--format", "json", "--symbols"]) == 0
    out = json.loads(capsys.readouterr().out)
    tables = {t["name"]: t for t in out["tables"]}
    assert tables["customers"]["doc"] == "One row per customer."
    assert {c["name"]: c["type"] for c in tables["customers"]["columns"]}["name"] == "string"


@pytest.mark.parametrize(
    "a, b",
    [("int", "INTEGER"), ("varchar(50)", "string"), ("timestamp", "timestamp with time zone"),
     ("decimal(10,2)", "numeric"), ("bool", "BOOLEAN"), ("text", "character varying(255)")],
)  # fmt: skip
def test_base_type_synonyms(a, b):
    assert base_type(a) == base_type(b)


def test_base_type_differs():
    assert base_type("int") != base_type("string")
    assert base_type("date") != base_type("timestamp")


def project(tmp_path, yml: str, files: dict[str, str] | None = None) -> Path:
    (tmp_path / "dbt").mkdir()
    (tmp_path / "dbt" / "dbt_project.yml").write_text("name: p\n")
    (tmp_path / "dbt" / "models").mkdir()
    (tmp_path / "dbt" / "models" / "schema.yml").write_text(yml)
    for name, text in (files or {}).items():
        (tmp_path / "dbt" / "models" / name).write_text(text)
    return tmp_path / "dbt"


ORDERS_YML = """
models:
  - name: orders
    description: Orders.
    columns:
      - name: order_id
        data_type: bigint
"""


def compile_here(tmp_path, text, name="s.txt"):
    f = tmp_path / name
    f.write_text(text)
    return compile_sources([(str(f), text)])


def test_names_match_ignoring_case(tmp_path):
    project(tmp_path, ORDERS_YML)
    s = compile_here(tmp_path, "# @dbt: dbt\n\nOrders\n-\nORDER_ID int\n")
    assert not s.diagnostics
    assert s.tables["Orders"].dbt.doc == "Orders."


def test_dbt_type_replaces_default_field_type(tmp_path):
    project(tmp_path, ORDERS_YML)
    s = compile_here(tmp_path, "# @dbt: dbt\n\norders\n-\norder_id\n\n[settings]\nDefaultFieldType varchar\n")
    assert not s.diagnostics  # a default type is no mismatch
    assert s.tables["orders"].columns["order_id"].shown_type() == "bigint"


def test_missing_project_is_an_error_on_the_directive(tmp_path):
    s = compile_here(tmp_path, "# Shop\n# @dbt: nowhere\n\norders\n-\nid int\n")
    assert [(d.line, d.severity) for d in s.diagnostics] == [(2, "error")]
    assert "no dbt_project.yml in" in s.diagnostics[0].message


def test_invalid_yml_is_an_error_naming_the_yml_line(tmp_path):
    project(tmp_path, "models:\n  - name: orders\n    description: [unclosed\n")
    s = compile_here(tmp_path, "# @dbt: dbt/dbt_project.yml\n\norders\n-\nid int\n")
    assert len(s.errors) == 1 and s.errors[0].line == 1
    assert "models/schema.yml:" in s.errors[0].message and "invalid YAML" in s.errors[0].message


def test_files_must_agree_on_the_project(tmp_path):
    project(tmp_path, ORDERS_YML)
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "dbt_project.yml").write_text("name: q\n")
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("# @dbt: dbt\n\norders\n-\norder_id int\n")
    b.write_text("# @dbt: other\n\nlines\n-\nid int\n")
    s = compile_sources([(str(a), a.read_text()), (str(b), b.read_text())])
    assert [d.message for d in s.errors] == [f"@dbt names a different dbt project than {a}:1"]


def test_unknown_doc_block_warns(tmp_path):
    project(tmp_path, "models:\n  - name: orders\n    description: \"{{ doc('nope') }}\"\n")
    s = compile_here(tmp_path, "# @dbt: dbt\n\norders\n-\nid int\n")
    assert [d.message for d in s.warnings] == ["dbt: no docs block named 'nope'"]
    assert s.tables["orders"].doc() == "{{ doc('nope') }}"


def test_same_name_twice_is_skipped(tmp_path):
    root = project(tmp_path, ORDERS_YML)
    (root / "models" / "more.yml").write_text("models:\n  - name: orders\n    description: Again.\n")
    s = compile_here(tmp_path, "# @dbt: dbt\n\norders\n-\nnote int\n")
    assert not s.diagnostics and s.tables["orders"].dbt is None


def test_dbml_directive_and_opt_out(tmp_path):
    project(tmp_path, ORDERS_YML)
    text = "// @dbt: dbt\n\nTable orders {\n  order_id int\n}\n\n// @dbt: none\nTable later {\n  id int\n}\n"
    s = compile_here(tmp_path, text, "s.dbml")
    assert not s.diagnostics
    assert s.tables["orders"].doc() == "Orders."
    assert s.tables["later"].dbt_skip


def test_convert_keeps_directives_and_writes_no_dbt_text(tmp_path):
    out = tmp_path / "s.dbml"
    assert main(["convert", str(ERD / "schema.txt"), "--to", "dbml", "-o", str(out)]) == 0
    text = out.read_text()
    assert "// @dbt: .." in text and "// @dbt: none" in text
    assert "One row per order" not in text and "Full name" in text  # only the schema's own comments


def test_build_is_deterministic(tmp_path):
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    assert main(["build", str(ERD), "-o", str(a)]) == 0
    assert main(["build", str(ERD), "-o", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()


def test_serve_reloads_when_the_yml_changes(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(FIXTURE, work)
    server, state = make_server(Project.open([work / "erd"]), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert not poll_once(state)
        yml = work / "models" / "marts" / "schema.yml"
        yml.write_text(yml.read_text().replace("One row per customer.", "A customer."))
        st = yml.stat()
        os.utime(yml, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        assert poll_once(state)
        docs = {t["name"]: t.get("doc") for t in state.model["tables"]}
        assert docs["customers"] == "A customer."
    finally:
        server.shutdown()
        server.server_close()
