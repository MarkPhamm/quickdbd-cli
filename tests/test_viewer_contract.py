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


def _function_body(name: str) -> str:
    m = re.search(rf"function {name}\(.*?\n  \}}\n", VIEWER, re.S)
    assert m, name
    return m.group(0)


def test_filter_recomputes_the_join_path():
    # A filter that hid a table on the shown path made pathSql look it up in the filtered model and throw (#246)
    body = _function_body("applyFilter")
    recompute = body.find("S.path.steps = Q.findPath(S.vm, S.focus, S.path.to)")
    assert recompute != -1, "applyFilter must recompute the path for the filtered view"
    assert recompute < body.find("showDetails(S.focus)")
