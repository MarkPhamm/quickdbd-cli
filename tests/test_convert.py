"""`qdbd convert` between QuickDBD and DBML: round trips, warned losses, the self-check and the CLI."""

import json
import tomllib
from pathlib import Path

import pytest

from quickdbd_cli import convert as conv
from quickdbd_cli.cli import main
from quickdbd_cli.parser import compile_sources
from quickdbd_cli.project import Project

ROOT = Path(__file__).resolve().parent.parent
TEAM = (Path(__file__).parent / "fixtures" / "dbml" / "team.dbml").read_text()


def _sources(path: Path) -> list[tuple[str, str, str]]:
    project = Project.open([path])
    out = []
    for f in project.files:
        rel = f.relative_to(path).as_posix() if path.is_dir() else f.name
        out.append((str(f), rel, f.read_text(encoding="utf-8")))
    return out


def _demo_sources() -> list[str]:
    cat = tomllib.loads((ROOT / "gallery" / "demos.toml").read_text())
    paths = sorted({d["source"] for d in cat["demo"] if "source" in d})
    return [*sorted(str(p.relative_to(ROOT)) for p in (ROOT / "examples").glob("*.txt")), *paths]


@pytest.mark.parametrize("src", _demo_sources())
def test_round_trip_examples_and_demos(src):
    sources = _sources(ROOT / src)
    original = compile_sources([(d, t) for d, _, t in sources])
    to_dbml = conv.convert(sources, "dbml", split_groups=False)
    back = conv.convert([(k, k, v) for k, v in to_dbml.files.items()], "quickdbd", split_groups=False)
    again = compile_sources(list(back.files.items()))
    assert again.errors == []
    lost = to_dbml.lost | back.lost
    assert conv.canonical(again, lost) == conv.canonical(original, lost)
    kinds = {w.message.split(":")[0] for w in to_dbml.warnings}
    assert kinds <= {"table-level relationship", "alias", "settings"}, kinds


def test_dbml_to_quickdbd_teammate_style():
    res = conv.convert([("team.dbml", "team.dbml", TEAM)], "quickdbd", split_groups=False)
    (name, text), *_ = res.files.items()
    assert name == "team.txt"
    schema = compile_sources([(name, text)])
    assert schema.errors == []
    assert len(schema.tables) == 10 and len(schema.relationships) == 10
    visits = text.split("visits\n", 1)[1].split("\n\n", 1)[0]
    assert visits.count("FK - visits_trend.") == 3


@pytest.mark.parametrize("op", ["-0", "0-", "0-0", "-0<", ">0-", "-", "-<", ">-", ">-<"])
def test_quickdbd_operators_round_trip(op):
    text = f"a\n-\nid PK int\n\nb\n-\nid PK int\na_id int FK {op} a.id\n"
    sources = [("s.txt", "s.txt", text)]
    dbml = conv.convert(sources, "dbml", split_groups=False)
    assert dbml.warnings == []
    back = conv.convert([(k, k, v) for k, v in dbml.files.items()], "quickdbd", split_groups=False)
    assert conv.canonical(compile_sources(list(back.files.items())), set()) == conv.canonical(
        compile_sources([("s.txt", text)]), set()
    )


def test_dbml_only_operator_is_approximated_with_a_warning():
    text = "Table a {\n  id int [pk]\n}\nTable b {\n  a_id int\n}\nRef: b.a_id >? a.id\n"
    res = conv.convert([("s.dbml", "s.dbml", text)], "quickdbd", split_groups=False)
    assert [w.line for w in res.warnings if "relationship" in w.message] == [7]
    assert compile_sources(list(res.files.items())).errors == []


def test_tablegroup_split():
    text = (
        "Table a {\n  id int\n}\nTable b {\n  id int\n}\nTable c {\n  id int\n}\n"
        "TableGroup sales {\n  a\n}\nTableGroup ops {\n  b\n}\n"
    )
    src = [("s.dbml", "s.dbml", text)]
    split = conv.convert(src, "quickdbd", split_groups=True)
    assert sorted(split.files) == ["ops.txt", "s.txt", "sales.txt"]
    assert "a\n-" in split.files["sales.txt"] and "c\n-" in split.files["s.txt"]
    single = conv.convert(src, "quickdbd", split_groups=False)
    assert list(single.files) == ["s.txt"]
    assert [w.line for w in single.warnings if w.message.startswith("TableGroup")] == [10, 13]


def test_losses_are_warned():
    text = """\
Enum status {
  active
  gone
}
Table a [headercolor: #ff0000] {
  id int [pk]
  s status
  x int
  y int
  indexes {
    (x, y) [unique]
  }
  checks {
    `id > 0`
  }
}
Table b {
  a_id int [ref: > a.id]
}
Ref: b.a_id < a.id [delete: cascade]
"""
    res = conv.convert([("s.dbml", "s.dbml", text)], "quickdbd", split_groups=False)
    lines = sorted({w.line for w in res.warnings})
    assert {1, 5, 11, 13, 20} <= set(lines), [w.format() for w in res.warnings]
    out = res.files["s.txt"]
    assert "# enum status: active, gone" in out
    schema = compile_sources([("s.txt", out)])
    cols = schema.tables["a"].columns
    assert cols["x"].index and cols["y"].index


def test_defaults_round_trip():
    text = (
        "a\n-\nid PK int\ns string default=pending\nt datetime default=CURRENT_TIMESTAMP\nn int=0\n"
        "b bool default=TRUE\n"
    )
    sources = [("s.txt", "s.txt", text)]
    dbml = conv.convert(sources, "dbml", split_groups=False)
    out = dbml.files["s.dbml"]
    assert "default: 'pending'" in out and "default: `CURRENT_TIMESTAMP`" in out and "default: 0" in out
    back = conv.convert([("s.dbml", "s.dbml", out)], "quickdbd", split_groups=False)
    cols = compile_sources(list(back.files.items())).tables["a"].columns
    assert [cols[c].default for c in ("s", "t", "n", "b")] == ["pending", "CURRENT_TIMESTAMP", "0", "true"]


def test_docs_and_tags_round_trip():
    text = "# @tag: core\n# The customer.\n#   indented\nCustomer\n-\nId PK int # the key\n"
    sources = [("s.txt", "s.txt", text)]
    dbml = conv.convert(sources, "dbml", split_groups=False).files["s.dbml"]
    back = conv.convert([("s.dbml", "s.dbml", dbml)], "quickdbd", split_groups=False).files["s.txt"]
    t = compile_sources([("s.txt", back)]).tables["Customer"]
    assert t.tags == ["core"]
    assert [x.strip() for x in t.comments] == ["The customer.", "indented"]
    assert t.columns["Id"].comments == ["the key"]


def test_already_in_target_syntax_is_copied():
    res = conv.convert([("t.dbml", "t.dbml", TEAM)], "dbml", split_groups=False)
    assert res.files == {"t.dbml": TEAM}


def test_cli_convert_stdout_and_dir(tmp_path, capsys):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "team.dbml").write_text(TEAM)
    (tmp_path / "in" / "shop.txt").write_text("shop\n-\nid PK int\n\n[layout]\nshop 10 20\n")
    assert main(["convert", str(tmp_path / "in" / "team.dbml"), "--to", "quickdbd"]) == 0
    out = capsys.readouterr().out
    assert "guests\n-\n" in out
    assert main(["convert", str(tmp_path / "in"), "--to", "dbml", "-o", str(tmp_path / "out")]) == 0
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["qdbd.layout.json", "shop.dbml", "team.dbml"]
    assert json.loads((tmp_path / "out" / "qdbd.layout.json").read_text())["tables"]["shop"] == {"x": 10, "y": 20}
    assert main(["check", str(tmp_path / "out")]) == 0


def test_cli_convert_self_check_failure(tmp_path, capsys, monkeypatch):
    src = tmp_path / "team.dbml"
    src.write_text(TEAM)
    real = conv._quickdbd_column

    def drop_pk(col, *a, **k):
        return real(col, *a, **k).replace(" PK", "")

    monkeypatch.setattr(conv, "_quickdbd_column", drop_pk)
    out = tmp_path / "out.txt"
    assert main(["convert", str(src), "--to", "quickdbd", "-o", str(out)]) == 1
    assert "converted schema differs from the input" in capsys.readouterr().err
    assert not out.exists()


def test_header_comments_round_trip():
    text = "// Shop schema.\n// Second line.\n\nTable a {\n  id int\n}\n"
    out = conv.convert([("s.dbml", "s.dbml", text)], "quickdbd", split_groups=False).files["s.txt"]
    assert out.startswith("# Shop schema.\n# Second line.\n\n")
    back = conv.convert([("s.txt", "s.txt", out)], "dbml", split_groups=False).files["s.dbml"]
    assert back.startswith("// Shop schema.\n// Second line.\n\n")


def _roundtrip_ok(sources, to, split=False):
    """Convert, then hold the CLI's self-check: the output compiles and matches, minus warned losses."""
    res = conv.convert(sources, to, split_groups=split)
    original = compile_sources([(d, t) for d, _, t in sources])
    again = compile_sources(list(res.files.items()))
    assert again.errors == [], [d.format() for d in again.errors]
    assert conv.canonical(again, res.lost) == conv.canonical(original, res.lost)
    return res


def test_cross_file_refs_convert_to_quickdbd():
    a = "Table orders {\n  id int [pk]\n  member_id int\n}\n"
    b = "Table members {\n  id int [pk]\n}\nRef: orders.member_id > members.id\n"
    res = _roundtrip_ok([("two/a.dbml", "a.dbml", a), ("two/b.dbml", "b.dbml", b)], "quickdbd")
    assert "member_id int FK >- members.id" in res.files["a.txt"]
    assert res.lost == set()


def test_mixed_folder_converts_to_quickdbd():
    a = "orders\n-\nid PK int\nmember_id int\n"
    b = "Table members {\n  id int [pk]\n}\nRef: members.id < orders.member_id\n"
    res = _roundtrip_ok([("m/a.txt", "a.txt", a), ("m/b.dbml", "b.dbml", b)], "quickdbd")
    assert res.files["a.txt"] == a  # already QuickDBD: copied as is, so the FK goes on the other end
    assert "id PK int FK -< orders.member_id" in res.files["b.txt"]
    assert res.lost == set() and res.warnings == []
    # A DBML file holding only a Ref between two QuickDBD tables: nowhere to write it.
    c = "Ref: orders.member_id > people.id\n"
    people = "people\n-\nid PK int\n"
    res = _roundtrip_ok([("m/a.txt", "a.txt", a), ("m/p.txt", "p.txt", people), ("m/c.dbml", "c.dbml", c)], "quickdbd")
    assert res.lost == {("rel", ("orders", "member_id"), ("people", "id"))}
    assert [(w.path, w.line) for w in res.warnings] == [("m/c.dbml", 1)]


def test_hash_in_notes_is_warned():
    text = "Table a [note: 'issue #12'] {\n  c varchar [note: 'hex like #fff']\n  d int [note: 'plain']\n}\n"
    res = _roundtrip_ok([("s.dbml", "s.dbml", text)], "quickdbd")
    assert sorted(w.line for w in res.warnings if "#" in w.message) == [1, 2]
    assert ("col", "a", "d", "doc") not in res.lost


def test_special_characters_in_defaults_and_docs():
    text = "Table a {\n  c varchar [default: '#000000']\n  d varchar [default: 'say hi now']\n}\n"
    res = _roundtrip_ok([("s.dbml", "s.dbml", text)], "quickdbd")
    cols = compile_sources(list(res.files.items())).tables["a"].columns
    assert (cols["c"].default, cols["d"].default) == ("#000000", "say hi now")
    quoted = "Table a {\n  q varchar [default: 'say \"hi\" now']\n}\n"
    res = _roundtrip_ok([("s.dbml", "s.dbml", quoted)], "quickdbd")
    assert [w.line for w in res.warnings if "default" in w.message] == [2]
    docs = "# path C:\\new\\table and ''' quotes\nCustomer\n-\nId PK int\n"
    res = _roundtrip_ok([("s.txt", "s.txt", docs)], "dbml")
    t = compile_sources(list(res.files.items())).tables["Customer"]
    assert t.comments == ["path C:\\new\\table and ''' quotes"]


def test_split_puts_the_header_in_a_written_file_and_avoids_name_clashes():
    text = (
        "// Shop.\n// @color core #ff0000\nEnum s {\n  a\n}\n"
        "Table a {\n  id int\n}\nTable b {\n  id int\n}\nTable c {\n  id int\n}\n"
        "TableGroup schema {\n  a\n}\nTableGroup g {\n  b\n  c\n}\n"
    )
    res = _roundtrip_ok([("schema.dbml", "schema.dbml", text)], "quickdbd", split=True)
    assert sorted(res.files) == ["g.txt", "schema.txt"]  # `schema` group and the source share a name: no clash
    whole = "".join(res.files.values())
    assert whole.count("# @color core #ff0000") == 1 and "# enum s: a" in whole and "# Shop." in whole
    grouped = "Table a {\n  id int\n}\nTableGroup g {\n  a\n}\n"
    other = "Table b {\n  id int\n}\nTableGroup g {\n  b\n}\n"
    res = _roundtrip_ok([("x/1.dbml", "1.dbml", grouped), ("x/2.dbml", "2.dbml", other)], "quickdbd", split=True)
    assert len(res.files) == 2 and all("-\nid int" in t for t in res.files.values())
    assert sorted(res.files) == ["g-2.txt", "g.txt"]


def test_dbml_output_quotes_types_dbdiagram_rejects():
    text = "a\n-\nx XML(Person.Schema)\ny decimal(10,2)\nz int\n"
    out = conv.convert([("s.txt", "s.txt", text)], "dbml", split_groups=False).files["s.dbml"]
    assert 'x "XML(Person.Schema)"' in out and "y decimal(10,2)" in out and "z int" in out
