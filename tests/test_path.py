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


# ------------------------------------------------------------------ composite keys, preferences, qualified names
def path_sql(files, a, b):
    from quickdbd_cli.parser import compile_sources

    m = model_json(compile_sources(files))
    steps = js("qdbdFindPath", m, a, b)
    return steps, js("qdbdPathSql", m, a, steps)


def test_dbml_composite_ref_joins_on_every_column():
    dbml = """Table v { a int [pk]
  b int [pk] }
Table t { a int
  b int }
Ref: t.(a, b) > v.(a, b)
"""
    steps, sql = path_sql([("s.dbml", dbml)], "t", "v")
    assert steps[0]["pairs"] == [["a", "a"], ["b", "b"]]
    assert sql == "FROM t\nJOIN v ON v.a = t.a AND v.b = t.b"


def test_quickdbd_fk_lines_covering_a_composite_pk_join_together():
    text = """offer
-
product_id PK int
offer_id PK int

detail
-
id PK int
product_id int FK >- offer.product_id
offer_id int FK >- offer.offer_id
"""
    steps, sql = path_sql([("s.txt", text)], "detail", "offer")
    assert sql == "FROM detail\nJOIN offer ON offer.product_id = detail.product_id AND offer.offer_id = detail.offer_id"


def test_role_playing_fks_stay_separate_joins():
    text = """language
-
language_id PK int

film
-
film_id PK int
language_id int FK >- language.language_id
original_language_id int NULL FK >- language.language_id
"""
    m = model_json(compile_text(text))
    assert all("k" not in r for r in m["rels"])
    steps = js("qdbdFindPath", m, "film", "language")
    assert steps[0]["pairs"] == [["language_id", "language_id"]]


def test_column_relationship_beats_an_earlier_table_level_one():
    text = """Product
-
ProductId PK int

OrderLine
rel >- Product
-
LineId PK int
ProductId int FK >- Product.ProductId
"""
    _, sql = path_sql([("s.txt", text)], "OrderLine", "Product")
    assert sql == "FROM OrderLine\nJOIN Product ON Product.ProductId = OrderLine.ProductId"


def test_dotted_names_are_qualified_identifiers():
    text = """"raw.users"
-
id PK int

"sales.Order"
-
id PK int
user_id int FK >- "raw.users".id
"""
    _, sql = path_sql([("s.txt", text)], "sales46Order", "raw46users")
    assert sql == 'FROM sales."Order"\nJOIN raw.users ON raw.users.id = sales."Order".user_id'


def test_cli_path_lists_every_composite_column(capsys):
    assert main(["path", "tests/fixtures/dbml/team.dbml", "--from", "rewards", "--to", "visits_trend"]) == 0
    out = capsys.readouterr().out
    assert "visits.(guest_sk, period_code, as_of) -> visits_trend.(guest_sk, period_code, as_of) (1:1)" in out
    assert "AND visits_trend.as_of = visits.as_of" in out
