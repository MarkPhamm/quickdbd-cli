"""Finding schema projects in a folder (targets.py), the same rules as the VS Code extension's target.ts."""

import json
import os
import shutil
from pathlib import Path

import pytest

from quickdbd_cli.dbt import HEADER
from quickdbd_cli.targets import MAX_SCAN, find_target, find_targets, schema_language

CASES = json.loads((Path(__file__).parent / "fixtures" / "targets" / "cases.json").read_text(encoding="utf-8"))
TABLE = "Customer\n-\nCustomerId PK int\n"
KEYED = TABLE + "x int FK >- Customer.CustomerId\n"
DBML = "Table guests {\n  id int [pk]\n}\n"


def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_find_target_cases(tmp_path, case):
    root = tree(tmp_path, case["files"])
    cwd, paths = find_target(root / case["file"], root / case.get("stopAt", ""))
    assert (cwd.resolve(), list(paths)) == ((root / case["expect"]["cwd"]).resolve(), case["expect"]["paths"])


def test_too_many_files_is_not_one_schema(tmp_path):
    root = tree(tmp_path, {f"t{i}.txt": TABLE for i in range(MAX_SCAN + 1)})
    assert find_target(root / "t0.txt", root) == (root, ("t0.txt",))


def test_schema_language(tmp_path):
    root = tree(tmp_path, {"a.dbml": "", "b.txt": DBML, "c.txt": KEYED, "notes.txt": "hi"})
    assert schema_language(root / "a.dbml", "", False) == "dbml"
    assert schema_language(root / "b.txt", DBML) == "dbml"
    assert schema_language(root / "c.txt", KEYED) == "quickdbd"
    assert schema_language(root / "notes.txt", "hi") is None
    assert schema_language(root / "b.txt", DBML, False) is None
    assert schema_language(root / "c.txt", "A\n-\nx int\n") is None  # a table but no key: not QuickDBD


def names(d):
    return [(t.name, t.kind, t.paths) for t in d.targets]


def test_find_targets_groups_and_skips(tmp_path):
    tree(
        tmp_path,
        {
            "erd/qdbd.layout.json": "{}",
            "erd/a.txt": KEYED,
            "erd/b.txt": KEYED,
            "shop.dbml": DBML,
            "requirements.txt": "flask\n",
            "notes/readme.txt": "hello",
            "node_modules/pkg/schema.txt": KEYED,
            ".venv/lib/schema.txt": KEYED,
            "build/schema.txt": KEYED,
        },
    )
    d = find_targets(tmp_path)
    assert d.truncated is None
    assert names(d) == [("erd", "schema", (".",)), ("shop", "schema", ("shop.dbml",))]
    assert find_targets(tmp_path / "notes").targets == []


def test_dbt_projects_and_generated_files(tmp_path):
    jaffle = Path(__file__).parent / "fixtures" / "jaffle"
    (tmp_path / "proj" / "target").mkdir(parents=True)
    (tmp_path / "proj" / "dbt_project.yml").write_text("name: jaffle_shop\n")
    shutil.copy(jaffle / "manifest.json", tmp_path / "proj" / "target" / "manifest.json")
    tree(tmp_path, {"proj/erd/staging.txt": f"{HEADER} from manifest.json.\n" + KEYED})
    d = find_targets(tmp_path)
    assert names(d) == [("erd", "schema", (".",)), ("proj (dbt)", "dbt", ("target/manifest.json",))]
    assert [t.generated for t in d.targets] == [True, False]
    assert d.targets[1].inputs() == [(tmp_path / "proj" / "target" / "manifest.json").resolve()]


def test_name_collisions_use_the_relative_path(tmp_path):
    tree(tmp_path, {"a/shop.txt": KEYED, "a/notes.txt": "x", "b/shop.txt": KEYED, "b/notes.txt": "x"})
    assert [t.name for t in find_targets(tmp_path).targets] == ["a/shop.txt", "b/shop.txt"]


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_outside_the_root_are_ignored(tmp_path):
    outside = tree(tmp_path / "outside", {"secret.txt": KEYED})
    root = tree(tmp_path / "ws", {"a.txt": KEYED, "notes.txt": "x"})
    (root / "link.txt").symlink_to(outside / "secret.txt")
    assert names(find_targets(root)) == [("a", "schema", ("a.txt",))]


def test_walk_budget_reports_a_reason(tmp_path):
    for i in range(30):
        (tmp_path / f"d{i}").mkdir()
    d = find_targets(tmp_path, max_dirs=5)
    assert d.truncated and "stopped after" in d.truncated
