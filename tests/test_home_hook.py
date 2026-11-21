"""The home-page MkDocs hook (hooks/home.py): the live mini diagram and the tour pages."""

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


def test_tour_has_a_diff_chapter():
    tour = re.search(r'<section class="qh-section qh-wrap qh-tour">(.*?)</section>', HOME_HTML, re.S).group(1)
    assert tour.count("<li") == 6
    assert 'data-page="diff"' in tour
    assert "data-diff-src=" in tour


def _model(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    return json.loads(re.search(r'id="qdbd-data">(.*?)</script>', text, re.S).group(1))["model"]


def test_build_tour(tmp_path):
    model = _model(home.build_tour(tmp_path))
    assert len(model["tables"]) == 13 and model["regions"]
    assert len({t["group"] for t in model["tables"]}) == 5  # one region per star schema, plus conformed
    # the tables and tag docs/javascripts/home-tour.js types, clicks and paths between
    driven = {"fct_airline_review", "dim_customer", "fct_seat_review", "fct_lounge_review", "dim_airport"}
    assert driven <= {t["id"] for t in model["tables"]}
    customer = next(t for t in model["tables"] if t["id"] == "dim_customer")
    assert customer["doc"].startswith("Conformed customer dimension.")
    assert "pii" in {g["name"] for g in model["tags"]}


def test_build_diff_tour(tmp_path):
    model = _model(home.build_diff_tour(tmp_path))
    d = model["diff"]
    assert d["base"] == "origin/main"
    assert (d["added"], d["changed"], d["removed"]) == (1, 2, ["dim_booking_channel"])
    states = {t["id"]: t["diff"]["state"] for t in model["tables"] if t.get("diff")}
    assert states["dim_route"] == "added" and states["fct_airline_review"] == "changed"


def test_build_dbt_tour(tmp_path):
    page = home.build_dbt_tour(tmp_path)
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    model = json.loads(re.search(r'id="qdbd-data">(.*?)</script>', text, re.S).group(1))["model"]
    assert len(model["tables"]) == 7
    orders = next(t for t in model["tables"] if t["id"] == "orders")
    assert orders["doc"] == "One row per order, open or complete.\nRecognised in revenue once status is paid."
    assert orders["tags"] == ["finance"]
    assert {c["name"]: c["type"] for c in orders["cols"]}["amount"] == "numeric(12,2)"
