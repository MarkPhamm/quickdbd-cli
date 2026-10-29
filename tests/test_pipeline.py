"""Layout, sidecar, rendering, export and CLI behaviour."""

import json
import shutil
from pathlib import Path

import pytest

from quickdbd_cli import export, layout
from quickdbd_cli.cli import main
from quickdbd_cli.html import render_page
from quickdbd_cli.measure import model_json, text_width
from quickdbd_cli.parser import compile_text
from quickdbd_cli.project import Project

ROOT = Path(__file__).resolve().parent.parent
SYNTH = ROOT / "examples" / "synthetic"
SAMPLE = ROOT / "examples" / "quickdbd-sample.txt"

SMALL = """Customer
-
CustomerId PK int
Name string

Order
-
OrderId PK int
CustomerId int FK >- Customer.CustomerId
"""


def _overlap(a, b):
    (ax, ay, aw, ah), (bx, by, bw, bh) = a, b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_text_width_uses_font_metrics():
    assert text_width("WWW", 12) > text_width("iii", 12) > 0
    assert text_width("Name", 12, bold=True) > text_width("Name", 12)


def test_model_sizes_tables_to_content():
    m = model_json(compile_text("T\n-\nAVeryLongColumnNameIndeed varchar(200)\n\nU\n-\nA int"))
    t, u = m["tables"]
    assert t["w"] > u["w"]
    assert t["h"] == m["style"]["headerH"] + m["style"]["rowH"] + m["style"]["bottomPad"]


def test_elk_layout_deterministic_and_non_overlapping():
    p = Project.open([SYNTH])
    m = model_json(p.compile())
    a = layout.elk_layout(m["tables"], m["rels"])
    b = layout.elk_layout(m["tables"], m["rels"])
    assert a == b and len(a) == 200
    by = {t["id"]: t for t in m["tables"]}
    rects = [(x, y, by[k]["w"], by[k]["h"]) for k, (x, y) in a.items()]
    assert not any(_overlap(r1, r2) for i, r1 in enumerate(rects) for r2 in rects[i + 1 :])


def test_big_layout_caps_overlap_removal_and_still_separates(monkeypatch):
    monkeypatch.setattr(layout, "BIG_LAYOUT", 100)  # take the >BIG_LAYOUT path on the 200-table schema
    m = model_json(Project.open([SYNTH]).compile())
    a = layout.elk_layout(m["tables"], m["rels"])
    assert a == layout.elk_layout(m["tables"], m["rels"]) and len(a) == 200
    by = {t["id"]: t for t in m["tables"]}
    rects = [(x, y, by[k]["w"], by[k]["h"]) for k, (x, y) in a.items()]
    assert not any(_overlap(r1, r2) for i, r1 in enumerate(rects) for r2 in rects[i + 1 :])


def test_place_missing_keeps_existing_and_avoids_overlap():
    m = model_json(compile_text(SMALL + "\nLine\n-\nId PK int\nOrderId int FK >- Order.OrderId\n"))
    fixed = {"Customer": (0, 0), "Order": (400, 0)}
    pos = layout.place_missing(m["tables"], m["rels"], fixed)
    assert pos["Customer"] == (0, 0) and pos["Order"] == (400, 0)
    by = {t["id"]: t for t in m["tables"]}
    new = (*pos["Line"], by["Line"]["w"], by["Line"]["h"])
    for k in fixed:
        assert not _overlap(new, (*pos[k], by[k]["w"], by[k]["h"]))
    # placed near its related table, not far away
    assert abs(pos["Line"][0] - 400) < 600 and abs(pos["Line"][1]) < 600


def test_sidecar_roundtrip_and_stable_format(tmp_path):
    f = tmp_path / "x.layout.json"
    layout.write_sidecar(f, {"B": (10, 20), "A": (1, 2)})
    assert layout.read_sidecar(f) == {"A": (1, 2), "B": (10, 20)}
    text = f.read_text()
    assert text.index('"A"') < text.index('"B"') and text.endswith("\n")


def test_sidecar_beats_qdbd_layout_section(tmp_path):
    src = tmp_path / "s.txt"
    src.write_text(SMALL + "\n[layout]\nCustomer 5 6\nOrder 7 8\n")
    p = Project.open([src])
    _, pos = p.build(p.compile())
    assert pos["Customer"] == [5, 6] and pos["Order"] == [7, 8]
    layout.write_sidecar(p.sidecar, {"Customer": (100, 200)})
    _, pos = p.build(p.compile())
    assert pos["Customer"] == [100, 200] and pos["Order"] == [7, 8]


def test_default_sidecar_paths(tmp_path):
    f = tmp_path / "schema.txt"
    f.write_text(SMALL)
    assert Project.open([f]).sidecar == tmp_path / "schema.layout.json"
    assert Project.open([tmp_path]).sidecar == tmp_path / "qdbd.layout.json"


def test_render_svg_contains_tables_and_markers():
    m = model_json(compile_text(SMALL))
    svg = export.render_svg(m, {"Customer": [0, 0], "Order": [400, 0]}, embed_font=False)
    assert svg.startswith("<svg") and "Customer" in svg and "OrderId" in svg
    assert svg.count('class="e"') == 1 and svg.count('class="t"') == 2


def test_focus_neighbourhood():
    m = model_json(compile_text(SMALL + "\nIsolated\n-\nId int\n"))
    assert sorted(export.focus_ids(m, "Customer", 1)) == ["Customer", "Order"]


def test_png_export(tmp_path):
    out = tmp_path / "c.png"
    assert main(["export", str(SAMPLE), "--focus", "Customer", "-o", str(out)]) == 0
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_export_caps_size(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(export, "MAX_PNG_SIDE", 300)
    out = tmp_path / "c.png"
    assert main(["export", str(SAMPLE), "-o", str(out)]) == 0
    head = out.read_bytes()
    w, h = int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    assert max(w, h) <= 300
    assert "--scale lowered" in capsys.readouterr().err


# ------------------------------------------------------------------ CLI


def test_check_ok(capsys):
    assert main(["check", str(SAMPLE)]) == 0
    assert capsys.readouterr().out.strip() == "No errors found. Good job!"


def test_check_errors_exit_1(tmp_path, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_text("T\n-\nA int foo\n")
    assert main(["check", str(bad)]) == 1
    assert "bad.txt:3: error: Unrecognized keyword 'foo'" in capsys.readouterr().err


def test_check_strict_warnings(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("T\n-\nA decimal(10, 2)\n")
    assert main(["check", str(f)]) == 0
    assert main(["check", "--strict", str(f)]) == 1


def test_check_format_github(tmp_path, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_text("T\n-\nA int foo\nB decimal(10, 2)\n")
    assert main(["check", "--format", "github", str(bad)]) == 1
    out = capsys.readouterr().out.splitlines()
    path = str(bad).replace(":", "%3A")  # a Windows drive colon is escaped in annotation properties
    assert f"::error file={path},line=3,title=qdbd::Unrecognized keyword 'foo'" in out
    assert any(line.startswith(f"::warning file={path},line=4,title=qdbd::QuickDBD would reject this") for line in out)


def test_check_format_github_strict_promotes_warnings(tmp_path, capsys):
    f = tmp_path / "w.txt"
    f.write_text("T\n-\nA decimal(10, 2)\n")
    assert main(["check", "--format", "github", "--strict", str(f)]) == 1
    assert capsys.readouterr().out.startswith(f"::error file={str(f).replace(':', '%3A')},line=3,")


def test_github_annotation_escaping():
    from quickdbd_cli.cli import _github_annotation
    from quickdbd_cli.model import Diagnostic

    d = Diagnostic("a,b:c.txt", 2, "50% bad\nnext", "warning")
    assert _github_annotation(d, "warning") == "::warning file=a%2Cb%3Ac.txt,line=2,title=qdbd::50%25 bad%0Anext"


def test_check_format_json(tmp_path, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_text("T\n-\nA int foo\n")
    assert main(["check", "--format", "json", str(bad)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False and data["errors"] == 1 and data["warnings"] == 0
    assert data["diagnostics"] == [
        {"path": str(bad), "line": 3, "severity": "error", "message": "Unrecognized keyword 'foo'"}
    ]


def test_check_symbols_list_tables_columns_and_rels(tmp_path, capsys):
    f = tmp_path / "shop.txt"
    f.write_text(SMALL)
    assert main(["check", "--format", "json", "--symbols", str(f)]) == 0
    r = json.loads(capsys.readouterr().out)
    order = next(t for t in r["tables"] if t["name"] == "Order")
    assert order["file"].endswith("shop.txt") and order["line"] < order["endLine"]
    assert [c["name"] for c in order["columns"]] and all(c["line"] > order["line"] for c in order["columns"])
    assert {(x["a"]["table"], x["b"]["table"]) for x in r["rels"]} == {("Order", "Customer")}
    assert main(["check", "--format", "json", str(f)]) == 0
    assert "tables" not in json.loads(capsys.readouterr().out)  # only with --symbols


def test_check_symbols_carry_types_keys_and_docs(tmp_path, capsys):
    f = tmp_path / "shop.txt"
    f.write_text("# People who buy things\n" + SMALL)
    assert main(["check", "--format", "json", "--symbols", str(f)]) == 0
    tables = {t["name"]: t for t in json.loads(capsys.readouterr().out)["tables"]}
    assert tables["Customer"]["doc"] == "People who buy things"
    assert "doc" not in tables["Order"]
    cols = {c["name"]: c for c in tables["Order"]["columns"]}
    assert {k: cols["OrderId"][k] for k in ("type", "pk", "fk")} == {"type": "int", "pk": True, "fk": False}
    assert cols["CustomerId"]["fk"] and not cols["CustomerId"]["pk"]


def test_check_stdin_file_uses_the_unsaved_text(tmp_path, capsys, monkeypatch):
    import io

    f = tmp_path / "shop.txt"
    f.write_text(SMALL)
    monkeypatch.setattr("sys.stdin", io.StringIO("Broken\n-\nId int FK >- Nope.Id\n"))
    assert main(["check", "--format", "json", "--stdin-file", str(f), str(tmp_path)]) == 1
    r = json.loads(capsys.readouterr().out)
    assert r["errors"] and "Nope" in r["diagnostics"][0]["message"]
    assert f.read_text() == SMALL
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["check", "--stdin-file", str(tmp_path / "other.txt"), str(f)]) == 2


def test_check_format_json_ok(capsys):
    assert main(["check", "--format", "json", str(SAMPLE)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"ok": True, "errors": 0, "warnings": 0, "diagnostics": []}


def test_build_is_deterministic_and_does_not_write_sidecar(tmp_path):
    work = tmp_path / "s"
    shutil.copytree(SYNTH, work)
    (work / "qdbd.layout.json").unlink(missing_ok=True)
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    assert main(["build", str(work), "-o", str(a)]) == 0
    assert main(["build", str(work), "-o", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    assert not (work / "qdbd.layout.json").exists()
    html = a.read_text()
    assert "<title>s</title>" in html and '"serve":false' in html
    # the VS Code icon, inline so the page stays one file
    assert '<link rel="icon" href="data:image/svg+xml,%3Csvg ' in html


def test_layout_command_writes_sidecar_and_reset(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text(SMALL)
    assert main(["layout", str(f)]) == 0
    side = tmp_path / "s.layout.json"
    data = json.loads(side.read_text())
    assert set(data["tables"]) == {"Customer", "Order"}
    layout.write_sidecar(side, {"Customer": (9999, 9999), "Order": (0, 0)})
    assert main(["layout", str(f), "--reset"]) == 0
    assert json.loads(side.read_text())["tables"]["Customer"] != {"x": 9999, "y": 9999}


def test_build_uses_but_never_rewrites_committed_sidecar(tmp_path):
    work = tmp_path / "s"
    shutil.copytree(SYNTH, work)
    side = work / "qdbd.layout.json"
    before = side.read_bytes()
    assert main(["build", str(work), "-o", str(tmp_path / "d.html")]) == 0
    assert side.read_bytes() == before
    html = (tmp_path / "d.html").read_text()
    customer = layout.read_sidecar(side)["Customer"]
    assert f'"Customer":[{customer[0]},{customer[1]}]' in html


def test_html_embeds_font_once():
    html = render_page(model_json(compile_text(SMALL)), {"Customer": [0, 0], "Order": [300, 0]}, "t")
    assert html.count("@font-face") == 2  # regular + bold, once each
    assert 'id="qdbd-font"' in html


def test_missing_path(capsys):
    assert main(["check", "nope/does-not-exist.txt"]) == 2


@pytest.mark.parametrize("bad_suffix", ["out.jpg"])
def test_export_rejects_unknown_format(tmp_path, bad_suffix):
    assert main(["export", str(SAMPLE), "-o", str(tmp_path / bad_suffix)]) == 2


DOCS = """# Customers who placed at least one order
Customer # one row per person
-
CustomerId PK int
# Contact address
Email string # verified
Name string
"""


def test_doc_comments_in_model():
    m = model_json(compile_text(DOCS))
    t = m["tables"][0]
    assert t["doc"] == "Customers who placed at least one order\none row per person"
    cols = {c["id"]: c for c in t["cols"]}
    assert cols["Email"]["doc"] == "Contact address\nverified"
    assert "doc" not in cols["Name"]


def test_doc_marks_only_in_viewer_not_exports():
    from quickdbd_cli.jsrt import runtime

    m = model_json(compile_text(DOCS))
    pos = {"Customer": [0, 0]}
    rt = runtime()
    rt.load("render.js")
    viewer = rt.call("qdbd.renderInner", m, pos, "full", {"docMarks": True})
    assert viewer.count('class="dm"') == 2  # table header + Email
    assert 'class="dm"' not in export.render_svg(m, pos, embed_font=False)


def test_model_has_explorer_groups_and_locations():
    p = Project.open([SYNTH])
    m = model_json(p.compile())
    assert sorted({t["group"] for t in m["tables"]}) == ["finance", "hr", "inventory", "marketing", "sales"]
    cust = next(t for t in m["tables"] if t["name"] == "Customer")
    assert cust["file"].endswith("examples/synthetic/sales.txt") and cust["line"] > 0
    single = model_json(compile_text(SMALL, "one.txt"))
    assert {t["group"] for t in single["tables"]} == {""}  # one file: flat list, no group headers


def test_page_has_explorer_and_details():
    html = render_page(model_json(compile_text(SMALL)), {"Customer": [0, 0], "Order": [300, 0]}, "t")
    for marker in ('id="explorer"', 'id="tree"', 'id="details"', 'id="q"'):
        assert marker in html


def test_page_has_share_link_controls():
    html = render_page(model_json(compile_text(SMALL)), {"Customer": [0, 0], "Order": [300, 0]}, "t")
    assert 'id="xlink"' in html and 'id="toast"' in html


def test_page_has_theme_toggle_and_exports_stay_light():
    m = model_json(compile_text(SMALL))
    pos = {"Customer": [0, 0], "Order": [300, 0]}
    html = render_page(m, pos, "t")
    assert 'id="xtheme"' in html and ':root[data-theme="dark"]' in html
    assert html.index("qdbd-theme") < html.index("</head>")  # theme applied before first paint
    svg = export.render_svg(m, pos, embed_font=False)
    assert "data-theme" not in svg and 'fill="#ffffff"' in svg and "#1e2228" not in svg


def test_drawio_export(tmp_path):
    import xml.etree.ElementTree as ET

    out = tmp_path / "erd.drawio"
    assert main(["export", str(SAMPLE), "-o", str(out)]) == 0
    root = ET.parse(out).getroot()
    assert root.tag == "mxfile"
    cells = list(root.iter("mxCell"))
    tables = [c for c in cells if "shape=table;" in (c.get("style") or "")]
    edges = [c for c in cells if c.get("edge") == "1"]
    assert sorted(t.get("value") for t in tables) == sorted(
        ["Customer", "Order", "OrderLine", "Product Catalog", "Product", "Address", "Wishlist"]
    )
    ids = {c.get("id") for c in cells}
    assert len(edges) == 7 and all(e.get("source") in ids and e.get("target") in ids for e in edges)
    styles = " ".join(e.get("style") for e in edges)
    for arrow in ("ERmany", "ERmandOne", "ERzeroToOne", "ERzeroToMany"):
        assert arrow in styles
    values = {c.get("value") for c in cells}
    assert "PK,FK" in values  # OrderLine.OrderId
    assert any(v and v == "CreatedAt  [=GETUTCDATE()] : datetime" for v in values)


def test_drawio_export_with_selection(tmp_path, capsys):
    out = tmp_path / "x.drawio"
    assert main(["export", str(SYNTH), "-s", "Customer+1", "-o", str(out)]) == 0
    assert "Wrote" in capsys.readouterr().out
    assert out.read_text().count("shape=table;") >= 2


def test_small_schema_layout_is_landscape():
    p = Project.open([SAMPLE])
    m = model_json(p.compile())
    pos = layout.elk_layout(m["tables"], m["rels"])
    w, h = layout._bbox(m["tables"], pos)
    assert w >= h  # chain-shaped schemas used to come out tall and narrow


def test_landscape_rotation_keeps_tables_upright():
    tables = [{"id": "a", "w": 100, "h": 50}, {"id": "b", "w": 100, "h": 50}]
    tall = {"a": (0, 0), "b": (0, 400)}
    out = layout._landscape(tables, tall)
    w, h = layout._bbox(tables, out)
    assert w > h
    assert layout._landscape(tables, out) == out  # already landscape: unchanged


def test_group_layout_keeps_folders_apart():
    p = Project.open([SYNTH])
    m = model_json(p.compile())
    pos = layout.group_layout(m["tables"], m["rels"])
    assert len(pos) == 200
    boxes = {}
    for t in m["tables"]:
        x, y = pos[t["id"]]
        b = boxes.setdefault(t["group"], [x, y, x + t["w"], y + t["h"]])
        b[:] = [min(b[0], x), min(b[1], y), max(b[2], x + t["w"]), max(b[3], y + t["h"])]
    rects = [(b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in boxes.values()]
    assert len(rects) == 5
    assert not any(_overlap(r1, r2) for i, r1 in enumerate(rects) for r2 in rects[i + 1 :])


def test_by_group_cli(tmp_path, capsys):
    work = tmp_path / "s"
    shutil.copytree(SYNTH, work)
    html = tmp_path / "g.html"
    assert main(["build", str(work), "--by-group", "-o", str(html)]) == 0
    assert '"regions":true' in html.read_text()
    svg = tmp_path / "g.svg"
    assert main(["export", str(work), "--by-group", "-o", str(svg)]) == 0
    assert svg.read_text().count('class="rg"') == 5
    drawio = tmp_path / "g.drawio"
    assert main(["export", str(work), "--regions", "-o", str(drawio)]) == 0
    assert drawio.read_text().count("verticalAlign=top;align=left;spacingLeft=12") == 5
    before = (work / "qdbd.layout.json").read_text()
    assert main(["layout", str(work), "--by-group"]) == 0
    assert (work / "qdbd.layout.json").read_text() != before


def test_regions_skip_ungrouped_tables():
    from quickdbd_cli.jsrt import runtime

    m = model_json(compile_text(SMALL, "one.txt"))
    rt = runtime()
    rt.load("render.js")
    assert rt.call("qdbd.regions", m, {"Customer": [0, 0], "Order": [300, 0]}, "full") == []
