"""Self-contained HTML page: model + positions + renderer + viewer, all inline."""

from __future__ import annotations

import json
from importlib import resources

from .export import font_css

CODEMIRROR = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16"


def _asset(name: str) -> str:
    return resources.files("quickdbd_cli").joinpath(f"assets/{name}").read_text(encoding="utf-8")


def _json_for_script(obj) -> str:
    # Safe inside <script type="application/json">: no "</" sequences.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


BODY = """
<div id="app">
  {side}
  <div id="stage">
    <svg id="canvas" xmlns="http://www.w3.org/2000/svg"><g id="vp"></g></svg>
    <div class="explorer" id="explorer">
      <div class="exhead">
        <button id="extoggle" title="Show/hide table list">&#9776;</button>
        <input id="q" type="search" placeholder="Search {count} tables  ( / )" autocomplete="off" spellcheck="false">
      </div>
      <div class="exfilter">
        <input id="filter" type="text" placeholder="Filter: orders+1  group:marts  !stg_*" autocomplete="off"
          spellcheck="false" title="{filter_help}">
        <div class="fstat" id="fstat"></div>
      </div>
      <div id="tree" class="tree"></div>
    </div>
    <aside class="details" id="details" aria-label="Table details">
      <button class="close" id="dclose" title="Close (Esc)">&times;</button>
      <div id="dbody"></div>
    </aside>
    <div class="bar">
      <div class="seg" id="modes" title="Collapse tables">
        <button data-mode="full" class="on">Full</button>
        <button data-mode="keys">Keys</button>
        <button data-mode="header">Names</button>
      </div>
      <div class="sep"></div>
      <button id="xlink" title="Copy a link to this exact view (filter, selected table, zoom)">Link</button>
      <div class="sep"></div>
      <button id="xsvg" title="Export SVG">SVG</button>
      <button id="xpng" title="Export PNG">PNG</button>
      <button id="xdrawio" title="Export an editable draw.io / diagrams.net file">draw.io</button>
      <div class="sep"></div>
      <button id="zout" title="Zoom out">&#8722;</button>
      <span class="zoomval" id="zoomval">100%</span>
      <button id="zin" title="Zoom in">+</button>
      <button id="zfit" title="Fit to screen">&#9678;</button>
    </div>
    <div class="minimap">
      <svg id="mini" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet"></svg>
    </div>
    <div class="tip" id="tip" role="tooltip"></div>
    <div class="toast" id="toast" role="status"></div>
    <div class="diffbar" id="diffbar"></div>
    <div class="hint">{hint}</div>
  </div>
</div>
"""

SIDE = """
<div id="side">
  <div class="tabs" id="tabs"></div>
  <div class="banner" id="banner">File changed on disk while you have unsaved edits.
    <button id="keepmine">Keep mine</button><button id="reload">Reload from disk</button></div>
  <div id="editor"></div>
  <div id="problems"></div>
</div>
"""


FILTER_HELP = (
    "dbt-style selectors. +x: x and what it references. x+: x and what references it. "
    "N+x+N: hops. group:/file:/col: methods. a,b: both. !x: exclude."
)


def render_page(model: dict, positions: dict, title: str, serve: bool = False) -> str:
    data = {"model": model, "positions": positions, "serve": serve, "title": title}
    hint = (
        "Drag tables to move them (saved). Click a table to focus. Esc clears."
        if serve
        else "Click a table to focus its relationships. Esc clears. Scroll to zoom, drag to pan."
    )
    body = BODY.format(side=SIDE if serve else "", count=len(model["tables"]), hint=hint, filter_help=FILTER_HELP)
    head_extra = ""
    scripts = ""
    if serve:
        head_extra = f'<link rel="stylesheet" href="{CODEMIRROR}/codemirror.min.css">'
        scripts = (
            f'<script src="{CODEMIRROR}/codemirror.min.js"></script>'
            f'<script src="{CODEMIRROR}/addon/mode/simple.min.js"></script>'
            f"<script>{_asset('editor.js')}</script>"
        )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="generator" content="qdbd">'
        f"<title>{_escape(title)}</title>"
        # The font CSS lives in its own <style> so the viewer can reuse it for SVG/PNG export
        # instead of embedding the fonts a second time.
        f'<style id="qdbd-font">{font_css()}</style>'
        f"<style>{_asset('style.css')}</style>{head_extra}</head><body>"
        f"{body}"
        f'<script type="application/json" id="qdbd-data">{_json_for_script(data)}</script>'
        f"<script>{_asset('render.js')}</script>"
        f"<script>{_asset('viewer.js')}</script>"
        f"{scripts}</body></html>\n"
    )
