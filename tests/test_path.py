"""Path finder (render.js findPath / pathSql) and `qdbd path`."""

from quickdbd_cli.cli import main
from quickdbd_cli.jsrt import runtime
from quickdbd_cli.measure import model_json
from quickdbd_cli.parser import compile_text

SCHEMA = """customers
-
customer_id PK int

"Order"
-
order_id PK int
customer_id int FK >- customers.customer_id

payments
-
payment_id PK int
order_id int FK >- Order.order_id

island
-
id PK int
"""


def js(fn, *args):
    rt = runtime()
    rt.load("render.js")
    return rt.call(fn, *args)


def test_find_path_both_directions():
    m = model_json(compile_text(SCHEMA))
    steps = js("qdbdFindPath", m, "payments", "customers")
    assert [(s["from"]["t"], s["from"]["c"], s["to"]["t"], s["to"]["c"]) for s in steps] == [
        ("payments", "order_id", "Order", "order_id"),
        ("Order", "customer_id", "customers", "customer_id"),
    ]
    back = js("qdbdFindPath", m, "customers", "payments")
    assert [s["to"]["t"] for s in back] == ["Order", "payments"]
    assert js("qdbdFindPath", m, "payments", "island") is None
    assert js("qdbdFindPath", m, "payments", "payments") == []


def test_path_sql_quotes_reserved_words():
    m = model_json(compile_text(SCHEMA))
    steps = js("qdbdFindPath", m, "payments", "customers")
    assert js("qdbdPathSql", m, "payments", steps) == (
        "FROM payments\n"
        'JOIN "Order" ON "Order".order_id = payments.order_id\n'
        'JOIN customers ON customers.customer_id = "Order".customer_id'
    )


def test_cli_path(tmp_path, capsys):
    f = tmp_path / "s.txt"
    f.write_text(SCHEMA)
    assert main(["path", str(f), "--from", "payments", "--to", "customers"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("payments -> customers: 2 join(s)")
    assert "payments.order_id -> Order.order_id (N:1)" in out
    assert 'JOIN "Order" ON' in out
    assert main(["path", str(f), "--from", "payments", "--to", "island"]) == 1
    assert "No relationship path" in capsys.readouterr().out
    assert main(["path", str(f), "--from", "nope", "--to", "island"]) == 1
