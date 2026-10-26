"""Table tags (`# @tag`, name prefixes, `# @dbt-tags`) and their header colours."""

import json

import pytest

from quickdbd_cli.dbt import import_dbt
from quickdbd_cli.diff import annotate_model, diff_schemas
from quickdbd_cli.export import render_drawio, render_svg
from quickdbd_cli.jsrt import runtime
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_sources, compile_text
from quickdbd_cli.tags import DEFAULT_COLORS, PALETTE, name_tag

SCHEMA = """# @color fact #123456
dim_customer
-
id PK int

# Orders, one per checkout
# @tag: gold, PII
fct_orders
-
id PK int
customer_id int FK >- dim_customer.id

Thing # @dbt-tags: nightly
-
id int

stg_shop__payments # @dbt-tags: nightly
-
id int

Plain
-
id int
"""


def tables(model):
    return {t["name"]: t for t in model["tables"]}


@pytest.fixture(scope="module")
def model():
    return model_json(compile_text(SCHEMA))


def test_directives_are_parsed_and_kept_out_of_docs():
    s = compile_text(SCHEMA)
    t = s.tables["fct_orders"]
    assert t.tags == ["gold", "pii"]
    assert t.comments == ["Orders, one per checkout"]
    assert s.tables["Thing"].dbt_tags == ["nightly"]
    assert s.tables["Thing"].comments == []
    assert s.tag_colors == {"fact": "#123456"}
    assert s.diagnostics == []


def test_precedence_explicit_then_name_then_dbt(model):
    t = tables(model)
    assert t["fct_orders"]["tags"] == ["gold", "pii"]  # explicit beats the fct_ prefix
    assert t["dim_customer"]["tags"] == ["dim"]  # name
    assert t["stg_shop__payments"]["tags"] == ["staging"]  # name beats dbt tags
    assert t["Thing"]["tags"] == ["nightly"]  # dbt tags
    assert "tags" not in t["Plain"] and "color" not in t["Plain"]


def test_colours_and_legend(model):
    t = tables(model)
    assert t["dim_customer"]["color"] == DEFAULT_COLORS["dim"]
    assert t["fct_orders"]["color"] == PALETTE[0]  # "gold": first non-default tag, by name
    legend = {g["name"]: (g["color"], g["count"]) for g in model["tags"]}
    assert legend == {
        "dim": (DEFAULT_COLORS["dim"], 1),
        "gold": (PALETTE[0], 1),
        "nightly": (PALETTE[1], 1),
        "pii": (PALETTE[2], 1),
        "staging": (DEFAULT_COLORS["staging"], 1),
    }
    assert "fact" not in legend  # @color for an unused tag doesn't add it


def test_color_with_trailing_comment():
    s = compile_text("# @color gold #b8860b   # optional: pick a colour\nA\n-\nid int\n")
    assert s.tag_colors == {"gold": "#b8860b"} and s.diagnostics == []


def test_color_override():
    m = model_json(compile_text("# @color dim #ABCDEF\ndim_x\n-\nid int\n"))
    assert m["tables"][0]["color"] == "#abcdef"


def test_no_tags_no_legend():
    assert "tags" not in model_json(compile_text("A\n-\nid int\n"))


@pytest.mark.parametrize(
    "line",
    ["# @color dim", "# @color dim red", "# @color #fff dim", "# @color dim #12345"],
)
def test_bad_color_is_a_warning(line):
    s = compile_text(f"{line}\nA\n-\nid int\n")
    assert [d.severity for d in s.diagnostics] == ["warning"]
    assert "Invalid @color" in s.diagnostics[0].message


def test_conflicting_colors_across_files():
    a = ("a.txt", "# @color dim #111111\nA\n-\nid int\n")
    b = ("b.txt", "# @color dim #222222\nB\n-\nid int\n")
    s = compile_sources([a, b])
    assert s.tag_colors == {"dim": "#111111"}
    assert [(d.path, d.severity) for d in s.diagnostics] == [("b.txt", "warning")]


@pytest.mark.parametrize(
    "name,tag",
    [
        ("dim_customer", "dim"),
        ("DimCustomer", "dim"),
        ("Dimension", None),
        ("fct_orders", "fact"),
        ("fact_sales", "fact"),
        ("FactSales", "fact"),
        ("Factory", None),
        ("stg_orders", "staging"),
        ("stg_shop__orders", "staging"),
        ("conformed__dim_airline", "dim"),
        ("int_orders_pivoted", "intermediate"),
        ("integer_table", None),
        ("raw_orders", "raw"),
        ("jaffle_shop.raw_orders", "raw"),
        ("dim_", None),
        ("Customer", None),
    ],
)
def test_name_tags(name, tag):
    assert name_tag(name) == tag


def test_tag_selector(model):
    rt = runtime()
    rt.load("render.js")
    assert rt.call("qdbdSelect", model, "tag:dim") == ["dim_customer"]
    assert rt.call("qdbdSelect", model, "tag:pii") == ["fct_orders"]
    assert rt.call("qdbdSelect", model, "tag:dim+") == ["dim_customer", "fct_orders"]
    assert rt.call("qdbdSelect", model, "tag:nope") == []


def test_svg_and_drawio_use_the_tag_colour(model):
    pos = {t["id"]: [i * 300, 0] for i, t in enumerate(model["tables"])}
    svg = render_svg(model, pos, embed_font=False)
    assert DEFAULT_COLORS["dim"] in svg and PALETTE[0] in svg and "#2b5797" in svg  # Plain stays blue
    xml = render_drawio(model, pos)
    assert "fillColor=" + DEFAULT_COLORS["dim"] in xml


def test_diff_colour_wins_over_tag():
    old = compile_text("A\n-\nid int\n")
    new = compile_text("A\n-\nid int\n\ndim_b\n-\nid int\n")
    m = annotate_model(model_json(new), diff_schemas(old, new), "main")
    b = next(t for t in m["tables"] if t["name"] == "dim_b")
    svg = render_svg(m, {"A": [0, 0], "dim_b": [300, 0]}, only=["dim_b"], embed_font=False)
    assert b["color"] == DEFAULT_COLORS["dim"] and "#2e7d32" in svg and DEFAULT_COLORS["dim"] not in svg


COLUMNS = """# @color pii #ff9800
orders
-
id PK int
# The discount.
# @tag: added
discount decimal
legacy varchar  # @tag: removed
email varchar  # @tag: PII
"""


def test_column_tags():
    s = compile_text(COLUMNS)
    cols = s.tables["orders"].columns
    assert cols["discount"].tags == ["added"] and cols["discount"].comments == ["The discount."]
    assert cols["legacy"].tags == ["removed"] and cols["legacy"].comments == []
    assert s.diagnostics == []
    m = model_json(s)
    c = {c["name"]: c for c in m["tables"][0]["cols"]}
    assert c["discount"]["color"] == DEFAULT_COLORS["added"] == "#2e7d32"
    assert c["legacy"]["color"] == DEFAULT_COLORS["removed"]
    assert c["email"]["tags"] == ["pii"] and c["email"]["color"] == "#ff9800"
    assert "tags" not in c["id"] and "color" not in c["id"]
    assert "tags" not in m["tables"][0]  # column tags don't tag (or colour) the table
    assert {g["name"]: g["count"] for g in m["tags"]} == {"added": 1, "pii": 1, "removed": 1}


def test_column_tags_render_select_and_keys_mode():
    m = model_json(compile_text(COLUMNS + "\nother\n-\nid int\n"))
    rt = runtime()
    rt.load("render.js")
    assert rt.call("qdbdSelect", m, "tag:removed") == ["orders"]
    pos = {"orders": [0, 0], "other": [300, 0]}
    svg = render_svg(m, pos, embed_font=False)
    assert 'fill="#c62828" fill-opacity=".1"' in svg and 'stroke="#c62828"' in svg  # tinted row, struck name
    keys = render_svg(m, pos, mode="keys", embed_font=False)
    assert ">legacy<" in keys and ">email<" in keys  # tagged columns stay visible with keys only
    xml = render_drawio(m, pos)
    assert "fontStyle=8;fontColor=#c62828;" in xml and "fontColor=#2e7d32;" in xml


def test_dbt_import_writes_dbt_tags(tmp_path):
    def node(uid, name, tags=None, config_tags=None):
        return {
            "unique_id": uid,
            "resource_type": "model",
            "name": name,
            "package_name": "shop",
            "fqn": ["shop", name],
            "original_file_path": f"models/{name}.sql",
            "description": "",
            "columns": {"id": {"name": "id", "description": "", "data_type": "int"}},
            "tags": tags or [],
            "config": {"tags": config_tags or []},
        }

    nodes = {
        "model.shop.orders": node("model.shop.orders", "orders", ["Nightly", "finance"], ["finance"]),
        "model.shop.dim_users": node("model.shop.dim_users", "dim_users", ["nightly"]),
        "model.shop.misc": node("model.shop.misc", "misc"),
    }
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps({"metadata": {"project_name": "shop"}, "nodes": nodes, "sources": {}}))
    res = import_dbt(mf)
    text = "".join(res.files.values())
    assert "# @dbt-tags: nightly, finance\norders\n" in text
    m = tables(model_json(compile_sources(list(res.files.items()))))
    assert m["orders"]["tags"] == ["nightly", "finance"]
    assert m["dim_users"]["tags"] == ["dim"]  # name beats dbt tags
    assert "tags" not in m["misc"]
