"""render.js details checked from Python (it runs in embedded V8 for exports)."""

import re

from quickdbd_cli import export
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_text


def _name_fill(svg: str, name: str) -> str:
    return re.search(r'<text class="tn"[^>]*fill="([^"]+)"[^>]*>' + name + "<", svg).group(1)


def test_light_header_colour_gets_dark_text():
    schema = compile_text("Table pale [headercolor: #ffeb3b] {\n  id int\n}\nTable dark {\n  id int\n}\n", "s.dbml")
    model = model_json(schema)
    pos = {t["id"]: [i * 300, 0] for i, t in enumerate(model["tables"])}
    svg = export.render_svg(model, pos)
    assert _name_fill(svg, "dark") == "#ffffff"
    assert _name_fill(svg, "pale") != "#ffffff"
