"""DBML files through the whole pipeline: detection, discovery, mixed folders, the model, check and diff."""

import json
import subprocess
from pathlib import Path

import pytest

from quickdbd_cli import diff
from quickdbd_cli.cli import main
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import syntax_of
from quickdbd_cli.project import Project

ROOT = Path(__file__).resolve().parent.parent
TEAM = (Path(__file__).parent / "fixtures" / "dbml" / "team.dbml").read_text()


def _quickdbd_files() -> list[Path]:
    dirs = [ROOT / "examples", ROOT / "gallery", ROOT / "tests" / "fixtures"]
    return sorted(f for d in dirs for f in d.rglob("*.txt"))


def test_syntax_of_existing_files_stay_quickdbd():
    files = _quickdbd_files()
    assert len(files) >= 15
    flipped = [
        str(f.relative_to(ROOT)) for f in files if syntax_of(f.name, f.read_text(encoding="utf-8")) != "quickdbd"
    ]
    assert flipped == []


@pytest.mark.parametrize(
    "text",
    [
        "Ref\n-\nid PK int\n",  # a QuickDBD table named Ref
        "# Table x {\nCustomer\n-\nid PK int\n",  # DBML-looking text in a comment
        "Customer\n-\nTable int\nRef: varchar\n",  # columns named Table and Ref:
        "Enum\n-\nid int\n",
    ],
)
def test_syntax_of_quickdbd_lookalikes(text):
    assert syntax_of("x.txt", text) == "quickdbd"


def test_syntax_of_dbml():
    assert syntax_of("team.txt", TEAM) == "dbml"
    assert syntax_of("team.dbml", "") == "dbml"
    assert syntax_of("x.txt", "Ref: a.id > b.id\n") == "dbml"
    assert syntax_of("x.txt", 'table "my table" as t {\n}\n') == "dbml"
    assert syntax_of("x.txt", "/* Table a {\n*/\nCustomer\n-\nid int\n") == "quickdbd"


def test_dbml_txt_with_a_broken_first_line(tmp_path, capsys):
    f = tmp_path / "team.txt"
    f.write_text("/ Use DBML to define your database structure\n" + TEAM)
    assert main(["check", str(f)]) == 1
    err = capsys.readouterr().err
    lines = [x for x in err.splitlines() if ": error: " in x]
    assert len(lines) == 1 and lines[0].startswith(f"{f}:1: error:")


def test_folder_discovers_dbml_and_mixed_links(tmp_path):
    (tmp_path / "a.txt").write_text(
        "visits_extra\n-\nid PK int\nguest_sk int FK >- guests.guest_sk\n\nnotes\n-\nid PK int\nlabel varchar\n"
    )
    (tmp_path / "b.dbml").write_text(TEAM + "\nRef: rewards.guest_sk > notes.id\n")
    (tmp_path / "readme.md").write_text("not a schema")
    project = Project.open([tmp_path])
    assert [f.name for f in project.files] == ["a.txt", "b.dbml"]
    schema = project.compile()
    assert [d.format() for d in schema.errors] == []
    names = {(schema.tables[r.a.table].name, schema.tables[r.b.table].name) for r in schema.valid_relationships()}
    assert ("visits_extra", "guests") in names
    assert ("rewards", "notes") in names


def test_duplicate_table_across_syntaxes(tmp_path):
    (tmp_path / "a.txt").write_text("guests\n-\nguest_sk PK int\n")
    (tmp_path / "b.dbml").write_text(TEAM)
    schema = Project.open([tmp_path]).compile()
    msgs = [d.format() for d in schema.errors]
    assert any("b.dbml:2: error: Table 'guests' already defined (first defined at" in m for m in msgs), msgs


def test_tablegroup_and_headercolor_in_model(tmp_path):
    (tmp_path / "s.dbml").write_text(
        "Table dim_a [headercolor: #ff0000] {\n  id int\n}\nTable b {\n  id int\n}\nTable c {\n  id int\n}\n"
        "TableGroup g {\n  b\n  c\n}\n"
    )
    (tmp_path / "other.txt").write_text("d\n-\nid int\n")
    model = model_json(Project.open([tmp_path]).compile())
    by = {t["name"]: t for t in model["tables"]}
    assert by["b"]["group"] == by["c"]["group"] == "g"
    assert by["dim_a"]["group"] == "s"
    assert by["d"]["group"] == "other"
    assert by["dim_a"]["color"] == "#ff0000"  # beats the dim_ name tag's colour
    assert by["dim_a"]["tags"] == ["dim"]


def test_check_symbols_dbml(tmp_path, capsys):
    f = tmp_path / "s.dbml"
    f.write_text("Table users {\n  id int [pk]\n  name varchar\n\n}\nTable p {\n  uid int [ref: > users.id]\n}\n")
    assert main(["check", "--format", "json", "--symbols", str(f)]) == 0
    report = json.loads(capsys.readouterr().out)
    users = next(t for t in report["tables"] if t["name"] == "users")
    assert (users["line"], users["endLine"]) == (1, 5)
    assert users["columns"][0] == {"name": "id", "line": 2, "type": "int", "pk": True, "fk": False}
    p = next(t for t in report["tables"] if t["name"] == "p")
    assert p["columns"][0]["fk"] is True


def test_diff_base_includes_dbml(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True)

    git("init", "-q", "-b", "main")
    (tmp_path / "s.dbml").write_text("Table old_one {\n  id int\n}\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "s.dbml").write_text("Table new_one {\n  id int\n}\n")
    old = diff.schema_at_ref("HEAD", [tmp_path])
    assert [t.name for t in old.tables.values()] == ["old_one"]


@pytest.mark.parametrize(
    "text",
    [
        "Customer\n-\ntable int # like {\nid PK int\n",  # a column named table, its comment ending in {
        "Project # the main one {\n-\nid PK int\n",
        "Customer\n-\nrecords int # {\n",
    ],
)
def test_syntax_of_quickdbd_comments_ending_in_a_brace(text):
    assert syntax_of("x.txt", text) == "quickdbd"


@pytest.mark.parametrize(
    "text",
    [
        "Table a { id int }\n",  # one-line tables
        "Table users\n{\n  id int\n}\n",  # brace on the next line
        "Table users [headercolor: #fff, note: 'x'] {\n  id int\n}\n",
        "records users(id, name) {\n  1, 'a'\n}\n",
    ],
)
def test_syntax_of_more_dbml(text):
    assert syntax_of("x.txt", text) == "dbml"


def test_syntax_of_unclosed_block_comment_is_fast():
    import time

    text = "Customer\n-\nid PK int\n" + "x int /* never closed\n" * 20000
    start = time.perf_counter()
    assert syntax_of("x.txt", text) == "quickdbd"
    assert time.perf_counter() - start < 0.5


def test_uppercase_txt_is_not_discovered(tmp_path):
    (tmp_path / "schema.txt").write_text("a\n-\nid PK int\n")
    (tmp_path / "README.TXT").write_text("Read me first.\n")
    (tmp_path / "Other.DBML").write_text("Table x {\n  id int\n}\n")
    assert [f.name for f in Project.open([tmp_path]).files] == ["schema.txt"]
