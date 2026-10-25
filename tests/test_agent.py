"""The `qdbd mcp` tools (agent.py), called directly on real fixtures."""

import shutil
import subprocess
from pathlib import Path

import pytest

from quickdbd_cli import agent
from quickdbd_cli.agent import ToolError, Workspace
from quickdbd_cli.targets import Target

REPO = Path(__file__).parent.parent
KEYED = "Customer\n-\nCustomerId PK int\nEmail string NULL  # where receipts go\n"


def call(ws, tool, **args):
    return getattr(agent, tool)(ws, args)


def text(ws, tool, **args):
    return call(ws, tool, **args).text


def copy(src: str, dst: Path) -> Path:
    s = REPO / src
    if s.is_dir():
        shutil.copytree(s, dst / s.name)
    else:
        shutil.copy(s, dst / s.name)
    return dst / s.name


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    copy("gallery/sakila", tmp_path)
    copy("tests/fixtures/dbml/team.dbml", tmp_path)
    (tmp_path / "team.layout.json").write_text("{}")  # a project of its own
    return Workspace(tmp_path)


def test_projects_and_the_project_argument(ws):
    out = text(ws, "list_projects")
    assert "2 project(s)" in out and "- sakila" in out and "- team" in out
    assert "sakila/schema.txt (quickdbd, 16 tables)" in out
    with pytest.raises(ToolError, match="pass `project`"):
        call(ws, "list_tables")
    with pytest.raises(ToolError, match="no project 'sales'; projects: sakila, team"):
        call(ws, "list_tables", project="sales")
    assert "16 table(s) in sakila" in text(ws, "list_tables", project="SAKILA")


def test_list_and_describe(ws):
    assert "film_actor: 3 columns" in text(ws, "list_tables", project="sakila", select="film*")
    out = text(ws, "describe_tables", project="sakila", tables=["Film", "nope_table"])
    assert "no table 'nope_table'" in out
    assert "## film  sakila/schema.txt:" in out
    assert "- language_id tinyint FK -> language.language_id" in out
    assert "original_language_id" in out and "null" in out
    assert "References:" in out and "film.language_id -> language.language_id (N:1)" in out
    team = text(ws, "describe_tables", project="team", tables=["visits_trend"])
    assert "composite key" in team


def test_search(ws):
    out = text(ws, "search_schema", project="sakila", query="language")
    assert "Tables:\n- language" in out and "film.original_language_id" in out
    assert "Nothing" in text(ws, "search_schema", project="sakila", query="zzzz")


def test_join_path_notes_and_alternatives(ws):
    out = text(ws, "join_path", project="sakila", **{"from": "film", "to": "language"})
    assert "JOIN language ON language.language_id = film.language_id" in out
    assert "also joinable via film.original_language_id -> language.language_id" in out
    team = text(ws, "join_path", project="team", **{"from": "rewards", "to": "visits_trend"})
    assert "composite key: join on every column" in team and "1:N: rows multiply" in team
    assert "AND visits_trend.as_of = visits.as_of" in team


def test_check_with_unsaved_content(ws, tmp_path):
    assert text(ws, "check_schema", project="team").startswith("OK: 1 file(s)")
    bad = (tmp_path / "team.dbml").read_text() + "\nTable broken {\n  x int [ref: > nowhere.id]\n}\n"
    out = text(ws, "check_schema", project="team", file="team.dbml", content=bad)
    assert out.startswith("FAILED") and "team.dbml:" in out
    assert (tmp_path / "team.dbml").read_text() != bad  # nothing written
    with pytest.raises(ToolError, match="not one of this project's schema files"):
        call(ws, "check_schema", project="team", file="../etc/passwd", content="x")
    new = text(ws, "check_schema", project="sakila", file="sakila/extra.txt", content=KEYED)
    assert new.startswith("OK: 2 file(s)")


def test_freshness(ws, tmp_path):
    assert "16 table(s)" in text(ws, "list_tables", project="sakila")
    (tmp_path / "sakila" / "extra.txt").write_text("Thing\n-\nThingId PK int\n")
    assert "17 table(s)" in text(ws, "list_tables", project="sakila")


def test_render_diagram(ws):
    res = call(ws, "render_diagram", project="sakila", focus="film", depth=1)
    assert res.image[:8] == b"\x89PNG\r\n\x1a\n" and "full mode" in res.text
    many = call(ws, "render_diagram", project="sakila")
    assert many.image and "16 table(s)" in many.text
    with pytest.raises(ToolError, match="no table"):
        call(ws, "render_diagram", project="sakila", focus="nope")


def test_selector_errors_are_tool_errors(ws):
    with pytest.raises(ToolError, match="unknown selector method"):
        call(ws, "list_tables", project="sakila", select="owner:x")
    with pytest.raises(ToolError, match="too long"):
        call(ws, "list_tables", project="sakila", select="x" * 600)


def test_syntax_reference():
    ws = Workspace(Path("."))
    assert "## Relationships" in text(ws, "syntax_reference")
    dbml = text(ws, "syntax_reference", syntax="dbml")
    assert "# DBML syntax" in dbml and "# QuickDBD syntax" not in dbml and "# Notes" in dbml


def test_refused_root():
    ws = Workspace(Path("/"), refused="too broad")
    with pytest.raises(ToolError, match="too broad"):
        call(ws, "list_projects")


def test_dbt_project_and_inferred_joins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target").mkdir()
    (tmp_path / "dbt_project.yml").write_text("name: jaffle_shop\n")
    for f in ("manifest.json", "catalog.json"):
        shutil.copy(REPO / "tests/fixtures/jaffle" / f, tmp_path / "target" / f)
    t = Target("jaffle (dbt)", "dbt", tmp_path, ("target/manifest.json",))
    plain = Workspace(tmp_path, t)
    assert "dbt manifest (live)" in text(plain, "list_projects")
    assert "No relationship path" in text(plain, "join_path", **{"from": "stg_payments", "to": "stg_customers"})
    with pytest.raises(ToolError, match="isn't in git"):
        call(plain, "diff_schema")
    inferred = Workspace(tmp_path, t, infer_fks=True)
    out = text(inferred, "join_path", **{"from": "stg_payments", "to": "stg_customers"})
    assert "inferred from column names" in out and "{{ ref('model') }}" in out


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    git("init", "-q", "-b", "main")
    (tmp_path / "shop.txt").write_text(KEYED)
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "feature")
    (tmp_path / "shop.txt").write_text(KEYED + "Name string\n")
    git("commit", "-qam", "feature")
    git("checkout", "-q", "main")
    (tmp_path / "shop.txt").write_text(KEYED + "Phone string\n")
    git("commit", "-qam", "main moves on")
    git("checkout", "-q", "feature")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_diff_against_the_branch_point(repo):
    ws = Workspace(repo)
    out = text(ws, "diff_schema", base="main")
    assert "merge-base" in out and "+ Name" in out and "Phone" not in out
    tip = text(ws, "diff_schema", base="main", merge_base=False)
    assert "- Phone" in tip
    assert "No schema changes" in text(ws, "diff_schema")
    edit = text(ws, "diff_schema", file="shop.txt", content=KEYED + "Name string\nAge int\n")
    assert "+ Age" in edit and "unsaved edit" in edit
    md = text(ws, "diff_schema", base="main", format="markdown")
    assert md.startswith("### Schema changes")
    with pytest.raises(ToolError, match="not a git ref"):
        call(ws, "diff_schema", base="--output=x")
