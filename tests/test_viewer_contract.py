"""The page elements the qdbd.dev live demo drives (docs/javascripts/home-tour.js).

The tour types into the search and filter boxes, clicks tree items, relationship lines and the card's Copy JOIN, uses
the path finder, and in its dbt chapter highlights the yml description, tag chips and column docs. Renaming any of
these breaks the tour silently, so they are pinned here.
"""

from pathlib import Path

from quickdbd_cli.cli import main

ROOT = Path(__file__).resolve().parent.parent
VIEWER = (ROOT / "src" / "quickdbd_cli" / "assets" / "viewer.js").read_text(encoding="utf-8")


def test_tour_contract(tmp_path):
    out = tmp_path / "d.html"
    assert main(["build", str(ROOT / "examples" / "quickdbd-sample.txt"), "-o", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    for el in ('id="q"', 'id="filter"', 'id="zfit"', 'id="rcard"', 'id="details"'):
        assert el in page, el
    for el in ('id="pathto"', 'id="pathsql"', 'id="rcopy"', 'class="hit"', 'class="ti"',
               'class="doc"', 'class="cd"', 'class="tchip'):
        assert el in VIEWER, el
