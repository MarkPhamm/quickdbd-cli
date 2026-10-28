"""MkDocs hook for the home page's live parts.

- The "From text to diagram" mini diagram is rendered by qdbd from the schema shown next to it (the
  <pre id="t-text"> in overrides/home.html), so the picture can't drift from the text. The page builds it as the text
  types, so it also gets which line of the text adds which table or row.
- The live demo drives the real viewer in an iframe, which must be same-origin: the AdventureWorks page is built into
  the site at assets/tour/adventureworks.html, for `mkdocs serve` as well as the Pages build.
"""

import html
import re
from pathlib import Path

from quickdbd_cli.export import render_svg
from quickdbd_cli.html import render_page
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_sources, compile_text
from quickdbd_cli.project import Project

ROOT = Path(__file__).resolve().parent.parent
HOME = ROOT / "overrides" / "home.html"
TOUR_SOURCE = ROOT / "gallery" / "adventureworks"
TOUR_PAGE = Path("assets") / "tour" / "adventureworks.html"
# The snippet's two tables side by side; any other table goes further right.
MINI_POSITIONS = {"Customer": (0, 10), "Order": (300, 0)}

_tour_html: str | None = None  # `mkdocs serve` rebuilds on every change; the tour page only needs laying out once


def mini_diagram(home_html: str) -> dict:
    """{"svg": the diagram, "steps": {0-based line of the snippet: ["t", table id] | ["r", table id, column id]}}"""
    m = re.search(r'<pre[^>]*\bid="t-text"[^>]*>(.*?)</pre>', home_html, re.S)
    if not m:
        raise ValueError('overrides/home.html has no <pre id="t-text">')
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
    schema = compile_text(text, "schema.txt")
    if schema.errors:
        raise ValueError(f"the home page schema doesn't compile: {schema.errors[0]}")
    model = model_json(schema)
    ids = {t["name"]: t for t in model["tables"]}
    pos, x = {}, max(p[0] for p in MINI_POSITIONS.values())
    for t in model["tables"]:
        if t["name"] not in MINI_POSITIONS:
            x += 300
        pos[t["id"]] = list(MINI_POSITIONS.get(t["name"], (x, 0)))
    steps = {}
    for name, table in schema.tables.items():
        tj = ids[name]
        steps[table.line - 1] = ["t", tj["id"]]
        cols = {c["name"]: c["id"] for c in tj["cols"]}
        for cname, col in table.columns.items():
            if not col.virtual and cname in cols:
                steps[col.line - 1] = ["r", tj["id"], cols[cname]]
    return {"svg": render_svg(model, pos, embed_font=False), "steps": dict(sorted(steps.items()))}


def build_tour(site_dir: Path) -> Path:
    """Write the AdventureWorks page the live demo drives; returns its path."""
    global _tour_html
    if _tour_html is None:
        project = Project.open([TOUR_SOURCE])
        schema = compile_sources(project.sources())
        if schema.errors:
            raise ValueError(f"the tour schema doesn't compile: {schema.errors[0]}")
        model, pos = project.build(schema, by_group=True)
        _tour_html = render_page(model, pos, "AdventureWorks")
    out = Path(site_dir) / TOUR_PAGE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_tour_html, encoding="utf-8")
    return out


def on_config(config, **kwargs):
    config.extra["home_mini"] = mini_diagram(HOME.read_text(encoding="utf-8"))
    return config


def on_post_build(config, **kwargs):
    build_tour(Path(config["site_dir"]))
