"""dbt-style table selectors (render.js `qdbd.select`), used by the page and `--select/--exclude`."""

import pytest

from quickdbd_cli.jsrt import runtime
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_sources

# customers <- orders <- order_items -> products ; payments -> orders ; audit (isolated)
FILES = [
    (
        "erd/marts/core.txt",
        """customers as c
-
customer_id PK int
email string

orders
-
order_id PK int
customer_id int FK >- customers.customer_id
""",
    ),
    (
        "erd/marts/items.txt",
        """order_items
-
item_id PK int
order_id int FK >- orders.order_id
product_id int FK >- products.product_id

products
-
product_id PK int
""",
    ),
    (
        "erd/staging/stg.txt",
        """payments
-
payment_id PK int
order_id int FK >- orders.order_id

audit
-
event_id PK int
""",
    ),
]


@pytest.fixture(scope="module")
def model():
    return model_json(compile_sources(FILES))


def sel(model, expr):
    rt = runtime()
    rt.load("render.js")
    return rt.call("qdbdSelect", model, expr)


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("", None),
        ("orders", ["orders"]),
        ("c", ["customers"]),  # alias
        ("ORD*", ["orders", "order_items"]),  # glob, case-insensitive
        ("*s", ["customers", "orders", "order_items", "products", "payments"]),
        ("+orders", ["customers", "orders"]),  # orders and what it references
        ("orders+", ["orders", "order_items", "payments"]),  # orders and what references it
        ("+order_items", ["customers", "orders", "order_items", "products"]),  # any depth
        ("1+order_items", ["orders", "order_items", "products"]),  # one hop
        ("customers+1", ["customers", "orders"]),
        ("customers+", ["customers", "orders", "order_items", "payments"]),
        ("+orders+", ["customers", "orders", "order_items", "payments"]),
        ("orders products", ["orders", "products"]),  # union
        ("group:staging", ["payments", "audit"]),
        ("group:marts", ["customers", "orders", "order_items", "products"]),  # folder prefix
        ("group:marts/items", ["order_items", "products"]),
        ("file:stg.txt", ["payments", "audit"]),
        ("col:order_id", ["orders", "order_items", "payments"]),
        ("col:order_id,group:marts", ["orders", "order_items"]),  # intersection
        ("group:marts !products", ["customers", "orders", "order_items"]),  # exclude
        ("!group:staging", ["customers", "orders", "order_items", "products"]),  # exclude only
        ("nothing_like_this", []),
    ],
)
def test_selectors(model, expr, expected):
    assert sel(model, expr) == expected


def test_unknown_method(model):
    with pytest.raises(Exception, match="unknown selector method"):
        sel(model, "tag:pii")


# ------------------------------------------------------------------ CLI --select / --exclude


def write_files(tmp_path):
    for name, text in FILES:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path / "erd"


def test_build_select_exclude(tmp_path, capsys):
    from quickdbd_cli.cli import main

    root = write_files(tmp_path)
    out = tmp_path / "d.html"
    assert main(["build", str(root), "-s", "group:marts", "--exclude", "products", "-o", str(out)]) == 0
    assert "(3 tables, 2 relationships)" in capsys.readouterr().out
    html = out.read_text()
    assert '"name":"orders"' in html and '"name":"products"' not in html and '"name":"payments"' not in html


def test_export_select_compacts_layout(tmp_path, capsys):
    from quickdbd_cli.cli import main

    root = write_files(tmp_path)
    assert main(["export", str(root), "-s", "+order_items", "-o", str(tmp_path / "x.svg")]) == 0
    assert "(4 tables)" in capsys.readouterr().out


def test_select_errors(tmp_path, capsys):
    from quickdbd_cli.cli import main

    root = write_files(tmp_path)
    assert main(["build", str(root), "-s", "nope", "-o", str(tmp_path / "d.html")]) == 1
    assert "no tables match 'nope'" in capsys.readouterr().err
    assert main(["build", str(root), "-s", "tag:x", "-o", str(tmp_path / "d.html")]) == 1
    assert "error: unknown selector method 'tag'" in capsys.readouterr().err


def test_selector_expr():
    from quickdbd_cli.project import selector_expr

    assert selector_expr(["a b", "c+"], ["d"]) == "a b c+ !d"
    assert selector_expr(None, None) == ""
