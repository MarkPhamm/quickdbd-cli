"""render.js details checked from Python (it runs in embedded V8 for exports)."""

import re
import textwrap

from quickdbd_cli import export
from quickdbd_cli.jsrt import runtime
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


# ------------------------------------------------------------------ lit relationships: labels and the card
ORDERS = """# Every order belongs to one customer.
Order as o
----
OrderId PK int IDENTITY
CustomerId int FK >- Customer.CustomerId
Status string="pending" # fulfilment state

Customer
-
CustomerId PK int
Email varchar(255) UNIQUE
"""


def js(fn, *args):
    rt = runtime()
    rt.load("render.js")
    return rt.call(fn, *args)


def rel_card(text, path="s.txt", i=0):
    return js("qdbdRelCard", model_json(compile_text(text, path)), i)


def test_rel_card_simple():
    card = rel_card(ORDERS)
    assert (card["from"], card["to"]) == ("Order.CustomerId", "Customer.CustomerId")
    assert (card["cardFrom"], card["cardTo"]) == ("*", "1")
    assert card["sentence"] == "Each Customer row has many Order rows"
    assert card["sql"] == 'FROM "Order"\nJOIN Customer ON Customer.CustomerId = "Order".CustomerId'


def test_rel_card_composite():
    dbml = "Table v { a int [pk]\n  b int [pk] }\nTable t { a int\n  b int }\nRef: t.(a, b) > v.(a, b)\n"
    card = rel_card(dbml, "s.dbml")
    assert card["from"] == "t.(a, b)"
    assert card["to"] == "v.(a, b)"
    assert card["sql"] == "FROM t\nJOIN v ON v.a = t.a AND v.b = t.b"


def test_rel_card_table_level():
    text = textwrap.dedent("""\
        A
        rel >- B
        -
        Id int

        B
        -
        ..
        Id int
        """)
    card = rel_card(text)
    assert card["from"] == "A"
    assert card["to"] == "B"
    assert card["sql"].endswith("-- table-level relationship: join columns not specified")


def edge_labels(text, pos):
    model = model_json(compile_text(text, "s.txt"))
    return js("qdbdEdgeLabels", model, pos, "full", model["rels"][0])


def test_edge_labels_sides():
    a, b = edge_labels(ORDERS, {"Customer": [0, 10], "Order": [300, 0]})
    assert [a["text"], b["text"]] == ["*", "1"]
    assert a["anchor"] == "end" and a["x"] < 300  # Order's left side faces Customer
    assert b["anchor"] == "start" and b["x"] > 189  # Customer's right side (width 189)


def test_edge_labels_self_ref():
    text = "Emp\n-\nId PK int\nBossId int FK >- Emp.Id\n"
    a, b = edge_labels(text, {"Emp": [0, 0]})
    assert a["anchor"] == b["anchor"] == "start"
    assert min(a["x"], b["x"]) > 0


def test_edge_labels_missing_position():
    assert edge_labels(ORDERS, {"Customer": [0, 0]}) is None


def test_rel_card_self_ref_aliases_the_parent():
    card = rel_card("Emp\n-\nId PK int\nBossId int FK >- Emp.Id\n")
    assert card["sql"] == "FROM Emp\nJOIN Emp AS Emp_2 ON Emp_2.Id = Emp.BossId"
