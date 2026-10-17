"""Layout, sidecar, rendering, export and CLI behaviour."""

import json
import shutil
from pathlib import Path

import pytest

from quickdbd_cli import export, layout
from quickdbd_cli.cli import main
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


def test_build_is_deterministic_and_does_not_write_sidecar(tmp_path):
    work = tmp_path / "s"
    shutil.copytree(SYNTH, work)
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    assert main(["build", str(work), "-o", str(a)]) == 0
    assert main(["build", str(work), "-o", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    assert not (work / "qdbd.layout.json").exists()
    html = a.read_text()
    assert "<title>s</title>" in html and '"serve":false' in html


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


def test_missing_path(capsys):
    assert main(["check", "nope/does-not-exist.txt"]) == 2


@pytest.mark.parametrize("bad_suffix", ["out.jpg"])
def test_export_rejects_unknown_format(tmp_path, bad_suffix):
    assert main(["export", str(SAMPLE), "-o", str(tmp_path / bad_suffix)]) == 2
