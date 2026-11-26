"""The page elements the qdbd.dev live demo drives (docs/javascripts/home-tour.js).

The tour types into the search and filter boxes, clicks tree items, relationship lines and the card's Copy JOIN, uses
the path finder, highlights the yml description, tag chips and column docs, and clicks the diff banner. Renaming any of
these breaks the tour silently, so they are pinned here.
"""

import re
from pathlib import Path

from quickdbd_cli.cli import main

ROOT = Path(__file__).resolve().parent.parent
VIEWER = (ROOT / "src" / "quickdbd_cli" / "assets" / "viewer.js").read_text(encoding="utf-8")


def test_tour_contract(tmp_path):
    out = tmp_path / "d.html"
    assert main(["build", str(ROOT / "examples" / "quickdbd-sample.txt"), "-o", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    for el in ('id="q"', 'id="filter"', 'id="zfit"', 'id="rcard"', 'id="details"', 'id="xrelationships"'):
        assert el in page, el
    for el in (
        'id="pathto"',
        'id="pathsql"',
        'id="rcopy"',
        'class="hit"',
        'class="ti"',
        'class="doc"',
        'class="cd"',
        'class="tchip',
        'id="diffonly"',
        'class="state ',
        '"qdbd-relationships"',
        '"relationships-hidden"',
    ):
        assert el in VIEWER, el


def test_toolbar_breakpoint_follows_the_stage_width():
    # serve's editor pane takes 420px of the window: a viewport media query left the toolbar over the search box
    css = (ROOT / "src" / "quickdbd_cli" / "assets" / "style.css").read_text(encoding="utf-8")
    m = re.search(r"@container stage \(max-width: (\d+)px\) \{\s*\.bar \{", css)
    assert m and "container: stage / inline-size" in css
    # explorer (16 + 270px) and the widest toolbar (~750px, with Regions) must fit side by side above it
    assert int(m.group(1)) >= 1060
    assert re.search(rf"var NARROW = {m.group(1)};", VIEWER), "fit() must know where the toolbar is"


def test_show_both_tables_selects_exact_ids():
    # a name glob (spaces as ?) also matched Order_Items, and 'sales:Orders' parsed as a selector method (#247)
    m = re.search(r'ev\.target\.id === "rboth".*?\n    \}', VIEWER, re.S)
    assert m
    assert '"id:" + ' in m.group(0)
    assert "replace(" not in m.group(0)
