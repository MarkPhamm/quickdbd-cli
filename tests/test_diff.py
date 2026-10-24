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
    assert tables["customers"]["diff"]["removedCols"] == ["legacy_flag"]
    assert "diff" not in tables["orders"] or tables["orders"]["diff"]["state"] == "changed"
    assert data["model"]["diff"]["removed"] == ["audit"]
    # diff: selector works with the annotations
    sel = repo / "s.html"
    assert main(["build", str(repo / "erd"), "--diff-base", "main", "-s", "diff:added", "-o", str(sel)]) == 0
    assert "(1 tables" in capsys.readouterr().out.splitlines()[-1]


def test_serve_diff_base_colours_the_live_model(repo):
    import os

    from quickdbd_cli.project import Project
    from quickdbd_cli.serve import make_server, poll_once

    server, state = make_server(Project.open([repo / "erd"]), port=0, embed=True, diff_base="main")
    server.server_close()
    tables = {t["name"]: t for t in state.model["tables"]}
    assert tables["products"]["diff"] == {"state": "added"}
    assert tables["customers"]["diff"]["removedCols"] == ["legacy_flag"]
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
