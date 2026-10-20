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


def _icon(d: str) -> str:
    """A 16px stroke icon, drawn in the toolbar's text colour."""
    return (
        '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">'
        f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="1.8"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )


ICONS = {
    "icon_menu": _icon("M4 6h16M4 12h16M4 18h16"),
    "icon_close": _icon("M6 6l12 12M18 6L6 18"),
    "icon_minus": _icon("M5 12h14"),
    "icon_plus": _icon("M12 5v14M5 12h14"),
    "icon_fit": _icon("M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"),
}


BODY = """
<div id="app">
  {side}
  <div id="stage">
    <svg id="canvas" xmlns="http://www.w3.org/2000/svg"><g id="vp"></g></svg>
    <div class="explorer" id="explorer">
      <div class="exhead">
        <button id="extoggle" title="Show/hide table list" aria-label="Show or hide the table list">{icon_menu}</button>
        <input id="q" type="search" placeholder="Search {count} tables  ( / )" autocomplete="off" spellcheck="false">
      </div>
      <div class="exfilter">
        <input id="filter" type="text" placeholder="Filter: orders+1  group:marts  !stg_*" autocomplete="off"
          spellcheck="false" title="{filter_help}">
        <div class="fstat" id="fstat"></div>
        <div class="tagbar" id="tagbar"></div>
      </div>
      <div id="tree" class="tree"></div>
    </div>
    <aside class="details" id="details" aria-label="Table details">
      <button class="close" id="dclose" title="Close (Esc)" aria-label="Close">{icon_close}</button>
      <div id="dbody"></div>
    </aside>
    <div class="bar">
      <div class="seg" id="modes" title="Collapse tables">
        <button data-mode="full" class="on">Full</button>
        <button data-mode="keys">Keys</button>
        <button data-mode="header">Names</button>
      </div>
      <div class="sep"></div>
      <button id="xregions" title="Shade an area per file / dbt folder">Regions</button>
      <button id="xlink" title="Copy a link to this exact view (filter, selected table, zoom)">Link</button>
      <div class="sep"></div>
      <button id="xsvg" title="Export SVG">SVG</button>
      <button id="xpng" title="Export PNG">PNG</button>
      <button id="xdrawio" title="Export an editable draw.io / diagrams.net file">draw.io</button>
      <div class="sep"></div>
      <button id="zout" title="Zoom out" aria-label="Zoom out">{icon_minus}</button>
      <span class="zoomval" id="zoomval">100%</span>
      <button id="zin" title="Zoom in" aria-label="Zoom in">{icon_plus}</button>
      <button id="zfit" title="Fit to screen" aria-label="Fit to screen">{icon_fit}</button>
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
    "N+x+N: hops. group:/file:/col:/tag: methods. a,b: both. !x: exclude."
)


# Read-only live view: refetch the model whenever the server's version changes. Relative URLs, so it
# also works behind a tunnel or a path prefix.
LIVE_JS = (
    "(function(){var v=null;new EventSource('events').onmessage=function(e){"
    "if(v!==null&&e.data!==v)fetch('state').then(function(r){return r.json();})"
    ".then(function(s){window.qdbdViewer.setData(s.model,s.positions);});v=e.data;};})();"
)


def render_page(model: dict, positions: dict, title: str, serve: bool = False, live: bool = False) -> str:
    """The self-contained page. ``serve``: editor pane and saved dragging. ``live``: read-only, but reloads
    when the server's schema changes (``qdbd serve --read-only``)."""
    data = {"model": model, "positions": positions, "serve": serve, "title": title}
    if serve:
        hint = "Drag tables to arrange them (saved). Click a table for details. Esc clears."
    elif live:
        hint = "Live, read-only view: updates when the schema changes. Drag tables to rearrange (not saved)."
    else:
        hint = (
            "Drag tables to rearrange (not saved). Click a table for details. Scroll to zoom, drag empty space to pan."
        )
    body = BODY.format(
        side=SIDE if serve else "", count=len(model["tables"]), hint=hint, filter_help=FILTER_HELP, **ICONS
    )
    head_extra = ""
    scripts = ""
    if serve:
        head_extra = f'<link rel="stylesheet" href="{CODEMIRROR}/codemirror.min.css">'
        scripts = (
            f'<script src="{CODEMIRROR}/codemirror.min.js"></script>'
            f'<script src="{CODEMIRROR}/addon/mode/simple.min.js"></script>'
            f"<script>{_asset('editor.js')}</script>"
        )
    elif live:
        scripts = f"<script>{LIVE_JS}</script>"
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
