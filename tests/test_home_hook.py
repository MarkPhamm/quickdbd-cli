"""The home-page MkDocs hook (hooks/home.py): the live mini diagram and the tour page."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "overrides").exists() or not (ROOT / "gallery").exists():  # the sdist ships tests, not the docs site
    pytest.skip("needs the git checkout's docs site and gallery/", allow_module_level=True)
sys.path.insert(0, str(ROOT / "hooks"))

import home  # noqa: E402

HOME_HTML = (ROOT / "overrides" / "home.html").read_text(encoding="utf-8")


def test_mini_diagram_steps():
    steps = home.mini_diagram(HOME_HTML)["steps"]
    assert steps == {
        1: ["t", "Order"],
        3: ["r", "Order", "OrderId"],
        4: ["r", "Order", "CustomerId"],
        5: ["r", "Order", "Status"],
        7: ["t", "Customer"],
        9: ["r", "Customer", "CustomerId"],
        10: ["r", "Customer", "Email"],
    }


def test_mini_diagram_svg():
    svg = home.mini_diagram(HOME_HTML)["svg"]
    assert 'data-id="Order"' in svg and 'data-id="Customer"' in svg
    assert svg.count('class="e"') == 1
    assert "@font-face" not in svg


def test_mini_diagram_relationship_text():
    (rel,) = home.mini_diagram(HOME_HTML)["rels"]
    assert rel["key"] == "Order|CustomerId|Customer|CustomerId"
    assert [label["text"] for label in rel["labels"]] == ["*", "1"]
    assert rel["card"]["sentence"] == "Each Customer row has many Order rows"


def test_build_tour(tmp_path):
    page = home.build_tour(tmp_path)
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    model = json.loads(re.search(r'id="qdbd-data">(.*?)</script>', text, re.S).group(1))["model"]
    assert len(model["tables"]) == 68
