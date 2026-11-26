"""`qdbd diff` and `build --diff-base`."""

import json
import subprocess

import pytest

from quickdbd_cli.cli import main
from quickdbd_cli.diff import diff_schemas, format_markdown
from quickdbd_cli.parser import compile_text

OLD = """customers
-
customer_id PK int
email string
legacy_flag bool

orders
-
order_id PK int
customer_id int FK >- customers.customer_id

audit
-
id PK int
"""

NEW = """customers
-
customer_id PK int
email varchar(255) UNIQUE
created_at datetime

orders
-
order_id PK int
customer_id int FK >- customers.customer_id
product_id int FK >- products.product_id

products
-
product_id PK int
"""


def test_diff_schemas():
    d = diff_schemas(compile_text(OLD, "a.txt"), compile_text(NEW, "b.txt"))
    assert d.added == ["products"]
    assert d.removed == ["audit"]
    changed = {c.name: c for c in d.changed}
    assert set(changed) == {"customers", "orders"}
    assert changed["customers"].added_cols == ["created_at"]
    assert changed["customers"].removed_cols == ["legacy_flag"]
    assert changed["customers"].changed_cols == {"email": ["type: string -> varchar(255)", "unique: no -> yes"]}
    assert changed["orders"].added_cols == ["product_id"]
    assert d.rels_added == ["orders.product_id -> products.product_id (N:1)"]
    assert d.rels_removed == []


def test_no_changes():
    d = diff_schemas(compile_text(OLD), compile_text(OLD))
    assert d.empty
    assert "No schema changes" in format_markdown(d, "a", "b")


def test_cli_two_paths_formats(tmp_path, capsys):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text(OLD)
    b.write_text(NEW)
    assert main(["diff", str(a), str(b)]) == 0
    out = capsys.readouterr().out
    assert "+ table products" in out and "- table audit" in out and "~ email: type: string -> varchar(255)" in out
    assert main(["diff", str(a), str(b), "--exit-code"]) == 1
    capsys.readouterr()
    assert main(["diff", str(a), str(b), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tables_added"] == ["products"]
    assert main(["diff", str(a), str(b), "--format", "markdown", "-o", str(tmp_path / "d.md")]) == 0
    md = (tmp_path / "d.md").read_text(encoding="utf-8")
    assert md.startswith("### Schema changes") and "| `customers` |" in md
    assert main(["diff", str(a), str(a), "--exit-code"]) == 0


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True, capture_output=True
        )

    git("init", "-q", "-b", "main")
    (tmp_path / "erd").mkdir()
    (tmp_path / "erd" / "core.txt").write_text(OLD)
    (tmp_path / "notes.txt").write_text("not a schema")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "erd" / "core.txt").write_text(NEW)
    return tmp_path


def test_cli_base_ref(repo, capsys):
    assert main(["diff", "--base", "main", str(repo / "erd")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Schema changes main -> working tree:")
    assert "1 table(s) added, 1 removed, 2 changed; 1 relationship(s) added, 0 removed" in out


def test_cli_bad_ref(repo, capsys):
    assert main(["diff", "--base", "nope-ref", str(repo / "erd")]) == 2
    assert "error:" in capsys.readouterr().err


def test_build_diff_base_marks_model(repo, capsys):
    out = repo / "d.html"
    assert main(["build", str(repo / "erd"), "--diff-base", "main", "-o", str(out)]) == 0
    html = out.read_text()
    data = json.loads(html.split('id="qdbd-data">', 1)[1].split("</script>", 1)[0])
    tables = {t["name"]: t for t in data["model"]["tables"]}
    assert tables["products"]["diff"] == {"state": "added"}
    assert tables["customers"]["diff"]["state"] == "changed"
    legacy = next(c for c in tables["customers"]["cols"] if c["name"] == "legacy_flag")
    assert tables["customers"]["diff"]["cols"][legacy["id"]] == "removed"
    assert tables["audit"]["diff"] == {"state": "removed"}  # drawn, in red
    assert "diff" not in tables["orders"] or tables["orders"]["diff"]["state"] == "changed"
    assert data["model"]["diff"]["removed"] == ["audit"]
    # diff: selector works with the annotations
    sel = repo / "s.html"
    assert main(["build", str(repo / "erd"), "--diff-base", "main", "-s", "diff:added", "-o", str(sel)]) == 0
    assert "(1 table," in capsys.readouterr().out.splitlines()[-1]


def test_serve_diff_base_colours_the_live_model(repo):
    import os

    from quickdbd_cli.project import Project
    from quickdbd_cli.serve import make_server, poll_once

    server, state = make_server(Project.open([repo / "erd"]), port=0, embed=True, diff_base="main")
    server.server_close()
    tables = {t["name"]: t for t in state.model["tables"]}
    assert tables["products"]["diff"] == {"state": "added"}
    assert "legacy_flag" in [c["name"] for c in tables["customers"]["cols"]]
    assert tables["audit"]["diff"] == {"state": "removed"} and "audit" in state.positions
    assert state.model["diff"]["base"] == "main" and state.model["diff"]["removed"] == ["audit"]
    # Edits are compared with the same base: back to the base text, nothing is marked.
    f = repo / "erd" / "core.txt"
    f.write_text(OLD)
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert poll_once(state)
    assert not any("diff" in t for t in state.model["tables"])
    assert state.model["diff"]["added"] == 0 and state.model["diff"]["removed"] == []


def test_serve_bad_diff_base_is_a_clean_error(repo, capsys):
    assert main(["serve", str(repo / "erd"), "--no-open", "--port", "0", "--diff-base", "nope-ref"]) == 2
    assert "error:" in capsys.readouterr().err


def test_refs_that_look_like_options_are_refused(repo, capsys):
    from quickdbd_cli import diff

    for bad in ("--output=x", "-p", "main\nHEAD"):
        with pytest.raises(diff.DiffError, match="not a git ref"):
            diff.sources_at_ref(bad, [repo / "erd"])
    assert diff.sources_at_ref("HEAD@{0}", [repo / "erd"])  # reflog syntax with braces still works
    assert not (repo / "x").exists()


def test_merge_base_is_where_the_branch_left(repo):
    from quickdbd_cli import diff

    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    fork = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "feature")
    git("commit", "-qam", "feature work")
    git("checkout", "-q", "main")
    (repo / "erd" / "core.txt").write_text(OLD + "\nlater\n-\nid PK int\n")
    git("commit", "-qam", "main moves on")
    git("checkout", "-q", "feature")
    assert diff.merge_base("main", [repo / "erd"]) == fork


@pytest.mark.parametrize(
    "old, new, changed",
    [
        ("note text", "note text [not null]", True),
        ("note text [not null]", "note text", True),
        ("note text", "note text [null]", False),  # DBML columns are nullable unless `not null`
    ],
)
def test_dbml_not_null_changes_are_reported(tmp_path, capsys, old, new, changed):
    a, b = tmp_path / "old.dbml", tmp_path / "new.dbml"
    a.write_text(f"Table orders {{\n  id int [pk]\n  {old}\n}}\n")
    b.write_text(f"Table orders {{\n  id int [pk]\n  {new}\n}}\n")
    assert main(["diff", str(a), str(b), "--exit-code"]) == int(changed)
    assert ("nullable:" in capsys.readouterr().out) == changed
    assert main(["diff", str(a), str(b), "--format", "json"]) == 0
    assert ("nullable" in capsys.readouterr().out) == changed


def test_base_ref_reads_unicode_filenames(tmp_path, capsys):
    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True, capture_output=True
        )

    git("init", "-q", "-b", "main")
    f = tmp_path / "café.dbml"
    f.write_text("Table customers {\n  id int [pk]\n}\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    for target in (f, tmp_path):
        assert main(["diff", "--base", "HEAD", str(target), "--exit-code"]) == 0, capsys.readouterr().out
    f.write_text("Table customers {\n  id int [pk]\n  name text\n}\n", encoding="utf-8")
    assert main(["diff", "--base", "HEAD", str(f), "--exit-code"]) == 1
    out = capsys.readouterr().out
    assert "+ name" in out and "+ table" not in out


def test_composite_ref_split_into_independent_refs_is_a_change(tmp_path, capsys):
    head = "Table parent {\n  a int [pk]\n  b int [pk]\n}\nTable child {\n  x int\n  y int\n}\n"
    comp = tmp_path / "comp.dbml"
    comp.write_text(head + "Ref: child.(x, y) > parent.(a, b)\n")
    split = tmp_path / "split.dbml"
    split.write_text(head + "Ref: child.x > parent.a\nRef: child.y > parent.b\n")
    swapped = tmp_path / "swapped.dbml"
    swapped.write_text(head + "Ref: child.y > parent.b\nRef: child.x > parent.a\n")
    assert main(["diff", str(comp), str(split), "--exit-code"]) == 1
    assert "child.(x, y) -> parent.(a, b)" in capsys.readouterr().out
    assert main(["diff", str(split), str(comp), "--exit-code"]) == 1
    capsys.readouterr()
    assert main(["diff", str(split), str(swapped), "--exit-code"]) == 0
    assert main(["diff", str(comp), str(comp), "--exit-code"]) == 0


def test_inline_and_top_level_refs_on_one_column_diff_empty(tmp_path, capsys):
    head = "Table parent {\n  a int [unique]\n  b int [unique]\n}\nTable child {\n  x int%s\n}\n%s"
    inline = tmp_path / "inline.dbml"
    inline.write_text(head % (" [ref: > parent.a, ref: > parent.b]", ""))
    top = tmp_path / "top.dbml"
    top.write_text(head % ("", "Ref: child.x > parent.a\nRef: child.x > parent.b\n"))
    assert main(["diff", str(inline), str(top), "--exit-code"]) == 0, capsys.readouterr().out


def test_base_ref_reports_every_table_when_the_last_schema_file_is_deleted(repo, capsys):
    core = repo / "erd" / "core.txt"
    core.unlink()
    for target in (core, repo / "erd"):
        assert main(["diff", "--base", "HEAD", str(target), "--exit-code"]) == 1
        out = capsys.readouterr().out
        assert "- table customers" in out and "+ table" not in out
    assert main(["diff", "--base", "HEAD", str(repo / "erd" / "missing.txt")]) == 2


def test_base_ref_with_one_deleted_input_keeps_the_surviving_files(repo, capsys):
    erd = repo / "erd"
    (erd / "users.txt").write_text("users\n-\nid int PK\n")
    subprocess.run(["git", "checkout", "-q", "--", "erd/core.txt"], cwd=repo, check=True)
    subprocess.run(["git", "add", "erd/users.txt"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "users"], cwd=repo, check=True)
    core, users = erd / "core.txt", erd / "users.txt"
    core.unlink()
    users.write_text("users\n-\nid int PK\nemail varchar\n")
    assert main(["diff", "--base", "HEAD", str(erd), "--exit-code"]) == 1
    want = capsys.readouterr().out
    assert "- table users" not in want and "+ email" in want
    for args in ([core, users], [users, core]):
        assert main(["diff", "--base", "HEAD", *map(str, args), "--exit-code"]) == 1
        out = capsys.readouterr().out
        assert "- table users" not in out and "+ email" in out
        assert out.splitlines()[-1] == want.splitlines()[-1]
    # a path that exists neither in git nor on disk is an input error, even next to a valid one
    assert main(["diff", "--base", "HEAD", str(users), str(erd / "typo.txt")]) == 2
    capsys.readouterr()
    # deleting every named input still reports all their tables as removed
    users.unlink()
    assert main(["diff", "--base", "HEAD", str(core), str(users), "--exit-code"]) == 1
    out = capsys.readouterr().out
    assert "- table users" in out and "- table customers" in out and "+ table" not in out


def test_base_ref_reads_uppercase_extensions(tmp_path, capsys):
    erd = tmp_path / "erd"
    erd.mkdir()
    (erd / "A.TXT").write_text("Alpha\n-\nId PK int\n")
    (erd / "b.txt").write_text("Beta\n-\nId PK int\nAId int FK >- Alpha.Id\n")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True)
    assert main(["diff", "--base", "HEAD", str(erd), "--exit-code"]) == 0, capsys.readouterr().out
