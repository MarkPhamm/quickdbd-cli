"""MkDocs hook for the home page's live parts.

- The "From text to diagram" mini diagram is rendered by qdbd from the schema shown next to it (the
  <pre id="t-text"> in overrides/home.html), so the picture can't drift from the text. The page builds it as the text
  types, so it also gets which line of the text adds which table or row.
- The icon (favicon, header, footer) is the VS Code extension's, from the package's assets/icon.svg; it is copied into
  the site rather than kept twice in git.
- The path and AI-agent sections show what qdbd's MCP tools (agent.py) answer about Sakila and AdventureWorks, run at
  build time.
- The live demo drives the real viewer in an iframe, which must be same-origin: the AdventureWorks DW page is built
  into the site at assets/tour/adventureworks-dw.html, for `mkdocs serve` as well as the Pages build.
"""

import html
import re
import shutil
from pathlib import Path

from quickdbd_cli.agent import Workspace, join_path, search_schema
from quickdbd_cli.export import render_svg
from quickdbd_cli.html import render_page
from quickdbd_cli.jsrt import runtime
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_sources, compile_text
from quickdbd_cli.project import Project

ROOT = Path(__file__).resolve().parent.parent
HOME = ROOT / "overrides" / "home.html"
ICON = ROOT / "src" / "quickdbd_cli" / "assets" / "icon.svg"
TOUR_SOURCE = ROOT / "gallery" / "adventureworks-dw"
AGENT_SOURCE = ROOT / "gallery" / "adventureworks"  # the AI-agent section's answers
PATH_SOURCE = ROOT / "gallery" / "sakila"  # the path section; scripts/gen_thumbnails.py PATH_SHOT shows the same join
TOUR_PAGE = Path("assets") / "tour" / "adventureworks-dw.html"
# The snippet's two tables side by side; any other table goes further right.
MINI_POSITIONS = {"Customer": (0, 10), "Order": (300, 0)}

_tour_html: str | None = None  # `mkdocs serve` rebuilds on every change; the tour page only needs laying out once


def mini_diagram(home_html: str) -> dict:
    """{"svg": the diagram, "steps": {0-based line of the snippet: ["t", table id] | ["r", table id, column id]},
    "rels": [{"key": "a|ac|b|bc", "labels": cardinality labels, "card": relationship card text}]}

    The docs page has no render.js, so the labels and card text come from it here, as in the viewer."""
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
    rt = runtime()
    rt.load("render.js")
    rels = [
        {
            "key": "|".join([r["a"]["t"], r["a"]["c"], r["b"]["t"], r["b"]["c"]]),
            "labels": rt.call("qdbdEdgeLabels", model, pos, "full", r),
            "card": rt.call("qdbdRelCard", model, i),
        }
        for i, r in enumerate(model["rels"])
    ]
    return {"svg": render_svg(model, pos, embed_font=False), "steps": dict(sorted(steps.items())), "rels": rels}


def agent_answers() -> dict:
    """{"search": first line of search_schema, "join": a join_path answer (AdventureWorks), "path_sql": the SQL of
    the path section's join (Sakila), "path_tables": that path's tables in order}."""
    ws = Workspace(AGENT_SOURCE)
    sql = join_path(Workspace(PATH_SOURCE), {"from": "payment", "to": "country"}).text.split("\n\n", 1)[1]
    return {
        "search": search_schema(ws, {"query": "country"}).text.splitlines()[0],
        "join": join_path(ws, {"from": "SalesOrderHeader", "to": "CountryRegion"}).text,
        "path_sql": sql,
        "path_tables": [line.split()[1] for line in sql.splitlines()],
    }


def build_tour(site_dir: Path) -> Path:
    """Write the AdventureWorks DW page the live demo drives; returns its path."""
    global _tour_html
    if _tour_html is None:
        project = Project.open([TOUR_SOURCE])
        schema = compile_sources(project.sources())
        if schema.errors:
            raise ValueError(f"the tour schema doesn't compile: {schema.errors[0]}")
        model, pos = project.build(schema, by_group=True)
        _tour_html = render_page(model, pos, "AdventureWorks DW")
    out = Path(site_dir) / TOUR_PAGE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_tour_html, encoding="utf-8")
    return out


def on_config(config, **kwargs):
    config.extra["home_mini"] = mini_diagram(HOME.read_text(encoding="utf-8"))
    config.extra["agent"] = agent_answers()
    config.extra["icon_svg"] = ICON.read_text(encoding="utf-8").strip().replace("<svg ", '<svg aria-hidden="true" ', 1)
    return config


def on_post_build(config, **kwargs):
    build_tour(Path(config["site_dir"]))
    shutil.copyfile(ICON, Path(config["site_dir"]) / "assets" / "img" / "icon.svg")
