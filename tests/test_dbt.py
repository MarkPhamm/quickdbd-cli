"""`qdbd import dbt`."""

import json
from pathlib import Path

from quickdbd_cli.cli import main
from quickdbd_cli.dbt import HEADER, import_dbt, norm_type, quote, write_result
from quickdbd_cli.parser import compile_sources, encode

JAFFLE = Path(__file__).parent / "fixtures" / "jaffle"


def compiled(result):
    s = compile_sources(list(result.files.items()))
    assert s.errors == [], [d.format() for d in s.errors]
    return s


def rels(schema):
    return sorted(
        (r.a.table, r.a.column, r.a.card, r.b.table, r.b.column, r.b.card) for r in schema.valid_relationships()
    )


# ------------------------------------------------------------------ real dbt output (jaffle_shop)


def test_jaffle_shop_real_manifest():
    res = import_dbt(JAFFLE / "manifest.json")  # catalog.json picked up automatically
    s = compiled(res)
    assert res.tables == 8 and res.relationships == 1
    assert rels(s) == [("orders", "customer_id", "many", "customers", "customer_id", "one")]
    cust = s.tables["customers"].columns
    assert cust["customer_id"].pk and cust["customer_id"].type == "INTEGER"  # unique + not_null tests -> PK
    assert s.tables["customers"].comments[0].startswith("This table has basic information about a customer")
    assert cust["first_name"].comments == ["Customer's first name. PII."]
    assert s.tables["stg_payments"].columns["payment_id"].pk


def test_jaffle_without_catalog_has_no_types(tmp_path):
    (tmp_path / "manifest.json").write_text((JAFFLE / "manifest.json").read_text())
    s = compiled(import_dbt(tmp_path / "manifest.json"))
    assert s.tables["customers"].columns["customer_id"].type is None


# ------------------------------------------------------------------ synthetic manifest: edge cases


def node(uid, name, rt="model", pkg="shop", fqn=None, cols=None, desc="", constraints=None, path=None):
    return {
        "unique_id": uid,
        "resource_type": rt,
        "name": name,
        "package_name": pkg,
        "fqn": fqn or [pkg, name],
        "original_file_path": path or f"models/{name}.sql",
        "description": desc,
        "columns": {
            c: {"name": c, "description": "", "data_type": t, "constraints": cons or []} for c, t, cons in (cols or [])
        },
        "constraints": constraints or [],
    }


def test_rel(uid, child, col, parent, field, name="relationships"):
    return {
        "unique_id": uid,
        "resource_type": "test",
        "name": uid,
        "package_name": "shop",
        "attached_node": child,
        "column_name": col,
        "test_metadata": {"name": name, "kwargs": {"column_name": col, "field": field, "to": "ref('x')"}},
        "depends_on": {"nodes": [parent, child] if parent != child else [child]},
    }


test_rel.__test__ = False  # helper, not a pytest test


def simple(uid, child, col, kind):
    return {
        "unique_id": uid,
        "resource_type": "test",
        "name": uid,
        "package_name": "shop",
        "attached_node": child,
        "column_name": col,
        "test_metadata": {"name": kind, "kwargs": {"column_name": col}},
        "depends_on": {"nodes": [child]},
    }


def manifest():
    src = {
        "unique_id": "source.shop.raw.users",
        "resource_type": "source",
        "name": "users",
        "source_name": "raw",
        "package_name": "shop",
        "fqn": ["shop", "raw", "users"],
        "original_file_path": "models/sources.yml",
        "description": "Raw users # from the app",
        "columns": {"id": {"name": "id", "description": "", "data_type": "integer"}},
    }
    nodes = {
        "model.shop.customers": node(
            "model.shop.customers",
            "customers",
            fqn=["shop", "marts", "customers"],
            path="models/marts/customers.sql",
            desc="One row per customer",
            cols=[("customer_id", "integer", [{"type": "primary_key"}]), ("user_id", "integer", None)],
        ),
        "model.shop.orders": node(
            "model.shop.orders",
            "orders",
            fqn=["shop", "marts", "orders"],
            path="models/marts/orders.sql",
            cols=[
                ("order_id", "integer", None),
                ("customer_id", "integer", None),
                (
                    "billing_customer_id",
                    "integer",
                    [{"type": "foreign_key", "to": "ref('customers')", "to_columns": ["customer_id"]}],
                ),
                ("Order Total", "numeric(10, 2)", None),
                ("created_at", "timestamp without time zone", None),
            ],
        ),
        "model.shop.order_details": node(
            "model.shop.order_details",
            "order_details",
            fqn=["shop", "marts", "order_details"],
            cols=[("order_id", "integer", None)],
            constraints=[{"type": "foreign_key", "columns": ["order_id"], "expression": "orders (order_id)"}],
        ),
        "model.shop.stg_users": node(
            "model.shop.stg_users", "stg_users", fqn=["shop", "staging", "stg_users"], cols=[("id", "integer", None)]
        ),
        "model.other.customers": node("model.other.customers", "customers", pkg="other", cols=[("id", "int", None)]),
        "seed.shop.countries": node("seed.shop.countries", "countries", rt="seed", cols=[("code", "text", None)]),
        "test.u1": simple("test.u1", "model.shop.orders", "order_id", "unique"),
        "test.n1": simple("test.n1", "model.shop.orders", "order_id", "not_null"),
        "test.u2": simple("test.u2", "model.shop.order_details", "order_id", "unique"),
        "test.r1": test_rel("test.r1", "model.shop.orders", "customer_id", "model.shop.customers", "customer_id"),
        "test.r2": test_rel(
            "test.r2", "model.shop.customers", "user_id", "source.shop.raw.users", "id", name="relationships_where"
        ),
        "test.r3": test_rel("test.r3", "model.shop.stg_users", "id", "source.shop.raw.users", "id"),
    }
    return {"metadata": {"project_name": "shop"}, "nodes": nodes, "sources": {src["unique_id"]: src}}


def run(tmp_path, **kw):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest()))
    return import_dbt(p, **kw)


def test_edge_cases(tmp_path):
    res = run(tmp_path)
    s = compiled(res)
    assert "customers" in s.tables and "other" not in str(list(s.tables))  # root package only by default
    src_id = encode("raw.users")
    assert s.tables[src_id].name == "raw.users"
    assert s.tables[src_id].comments == ["Raw users ＃ from the app"]  # '#' can't end the comment early
    orders = s.tables["orders"].columns
    assert orders["order_id"].pk and not orders["order_id"].unique  # unique+not_null -> PK
    assert s.tables["customers"].columns["customer_id"].pk  # primary_key constraint
    assert orders[encode("Order Total")].name == "Order Total" and orders[encode("Order Total")].type == "numeric(10,2)"
    assert orders["created_at"].type == "timestamp"
    assert rels(s) == sorted(
        [
            ("orders", "customer_id", "many", "customers", "customer_id", "one"),  # relationships test
            ("orders", "billing_customer_id", "many", "customers", "customer_id", "one"),  # column FK constraint
            ("order_details", "order_id", "one", "orders", "order_id", "one"),  # unique child -> one-to-one
            ("customers", "user_id", "many", src_id, "id", "one"),  # relationships_where to a source
            ("stg_users", "id", "many", src_id, "id", "one"),
        ]
    )
    assert res.relationships == 5


def test_all_packages_disambiguates_names(tmp_path):
    s = compiled(run(tmp_path, packages=["all"]))
    assert encode("other.customers") in s.tables and "customers" not in s.tables
    assert encode("shop.customers") in s.tables


def test_select_and_no_sources(tmp_path):
    res = run(tmp_path, select=["shop.marts.*"], sources=False)
    s = compiled(res)
    assert sorted(s.tables) == ["customers", "order_details", "orders"]
    assert any("not in selection" in x for x in res.skipped)


def test_split_by_folder_and_stale_cleanup(tmp_path):
    res = run(tmp_path, split=True)
    assert sorted(res.files) == ["marts.txt", "seeds.txt", "sources.txt", "staging.txt"]
    out = tmp_path / "erd"
    out.mkdir()
    (out / "old.txt").write_text(HEADER + " from x\n")
    (out / "mine.txt").write_text("# hand-written\nT\n-\nA int\n")
    write_result(res, out)
    assert not (out / "old.txt").exists() and (out / "mine.txt").exists()
    compiled(res)  # cross-file references resolve


def test_cli_import_then_build(tmp_path, capsys):
    out = tmp_path / "erd"
    assert main(["import", "dbt", str(JAFFLE), "-o", str(out)]) == 0
    assert "8 tables, 1 relationships" in capsys.readouterr().out
    assert main(["build", str(out), "-o", str(tmp_path / "erd.html")]) == 0
    assert (tmp_path / "erd.html").stat().st_size > 10_000


def test_cli_bad_manifest(tmp_path, capsys):
    bad = tmp_path / "manifest.json"
    bad.write_text("{}")
    assert main(["import", "dbt", str(bad)]) == 1
    assert "not a dbt manifest" in capsys.readouterr().err


def test_helpers():
    assert quote("order_id") == "order_id" and quote("Order Total") == '"Order Total"'
    assert norm_type("character varying(255)") == "varchar(255)"
    assert norm_type("NUMBER(38, 0)") == "NUMBER(38,0)"
    assert norm_type("struct<a int>") == "struct<a_int>"
    assert norm_type(None) is None


# ------------------------------------------------------------------ --infer-fks / --check


def test_infer_fks_on_jaffle():
    res = import_dbt(JAFFLE / "manifest.json", infer_fks=True)
    s = compiled(res)
    assert res.relationships == 4
    assert sorted(res.inferred) == [
        "raw_payments.order_id -> raw_orders.id",  # same raw_ prefix; parent key is plain `id`
        "stg_orders.customer_id -> stg_customers.customer_id",  # same stg_ prefix wins over marts customers
        "stg_payments.order_id -> stg_orders.order_id",
    ]
    assert "raw_orders.user_id" not in " ".join(res.inferred)  # no `users` table: nothing to link
    col = s.tables["stg_orders"].columns["customer_id"]
    assert col.fk and "inferred from the column name" in col.comments[-1]
    # declared relationships are untouched and not duplicated
    assert ("orders", "customer_id", "many", "customers", "customer_id", "one") in rels(s)


def infer_manifest():
    def m(uid, name, cols, fqn=None, pk=None):
        n = node(uid, name, fqn=fqn, cols=[(c, "int", [{"type": "primary_key"}] if c == pk else None) for c in cols])
        return n

    nodes = {
        "model.shop.dim_category": m("model.shop.dim_category", "dim_category", ["category_id"], pk="category_id"),
        "model.shop.categories": m(
            "model.shop.categories",
            "categories",
            ["category_id"],
            pk="category_id",
            fqn=["shop", "other", "categories"],
        ),
        "model.shop.fct_sales": m(
            "model.shop.fct_sales",
            "fct_sales",
            ["sale_id", "categoryId", "store_key", "owner_id", "region_id"],
            pk="sale_id",
        ),
        "model.shop.dim_stores": m("model.shop.dim_stores", "dim_stores", ["store_key"], pk="store_key"),
        "model.shop.people": m("model.shop.people", "people", ["id"]),
        "model.shop.owners_a": m("model.shop.owners_a", "a_owner", ["owner_id"], pk="owner_id"),
        "model.shop.dim_owner": m(
            "model.shop.dim_owner", "dim_owner", ["owner_id"], pk="owner_id", fqn=["shop", "x", "dim_owner"]
        ),
        "model.shop.dim_region": m("model.shop.dim_region", "dim_region", ["region_id"], pk="region_id"),
        "model.shop.dim_regions": m("model.shop.dim_regions", "dim_regions", ["region_id"], pk="region_id"),
        "model.shop.fct_owner": m(
            "model.shop.fct_owner", "fct_owner", ["owner_id"], pk="owner_id", fqn=["shop", "x", "fct_owner"]
        ),
    }
    return {"metadata": {"project_name": "shop"}, "nodes": nodes, "sources": {}}


def test_infer_rules(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(infer_manifest()))
    res = import_dbt(p, infer_fks=True)
    compiled(res)
    inferred = sorted(res.inferred)
    # camelCase `categoryId` -> category; both dim_category and categories match, the fct_ child's folder decides
    assert "fct_sales.categoryId -> dim_category.category_id" in inferred
    assert "fct_sales.store_key -> dim_stores.store_key" in inferred  # `_key` suffix, plural table
    # facts point at dimensions: dim_owner beats the same-layer fct_owner
    assert "fct_sales.owner_id -> dim_owner.owner_id" in inferred
    # region_id: dim_region and dim_regions tie on every rule -> skipped as ambiguous, never guessed
    assert not any(x.startswith("fct_sales.region_id") for x in inferred)
    assert any("fct_sales.region_id: ambiguous (dim_region, dim_regions)" in x for x in res.skipped)
    # single primary keys are never turned into FKs
    assert not any(x.startswith(("dim_category.", "dim_stores.")) for x in inferred)


def test_infer_off_by_default():
    res = import_dbt(JAFFLE / "manifest.json")
    assert res.inferred == [] and res.relationships == 1


def test_check_mode(tmp_path, capsys):
    out = tmp_path / "erd"
    assert main(["import", "dbt", str(JAFFLE), "-o", str(out), "--check"]) == 1  # nothing written yet
    assert "(missing)" in capsys.readouterr().err
    assert not out.exists()
    assert main(["import", "dbt", str(JAFFLE), "-o", str(out)]) == 0
    assert main(["import", "dbt", str(JAFFLE), "-o", str(out), "--check"]) == 0
    assert "Up to date" in capsys.readouterr().out
    assert main(["import", "dbt", str(JAFFLE), "-o", str(out), "--check", "--infer-fks"]) == 1
    err = capsys.readouterr().err
    assert "(out of date)" in err and "commit the result" in err
    (out / "old.txt").write_text(HEADER + " from x\n")
    assert main(["import", "dbt", str(JAFFLE), "-o", str(out), "--check"]) == 1
    assert "no longer generated" in capsys.readouterr().err


def test_layer_names():
    from quickdbd_cli.dbt import _layer

    assert _layer("stg_orders") == ("stg_", "orders")
    assert _layer("stg_jaffle_shop__orders") == ("stg_", "orders")
    assert _layer("conformed__dim_airline") == ("dim_", "airline")
    assert _layer("airlines_reviews__fct_airline_review") == ("fct_", "airline_review")
    assert _layer("bronze__achievements") == ("bronze__", "achievements")
    assert _layer("customers") == ("", "customers")


def test_infer_with_source_qualified_names(tmp_path):
    def m(uid, name, cols, pk=None, fqn=None):
        return node(uid, name, fqn=fqn, cols=[(c, "int", [{"type": "primary_key"}] if c == pk else None) for c in cols])

    nodes = {
        "model.shop.stg_jaffle_shop__customers": m(
            "model.shop.stg_jaffle_shop__customers",
            "stg_jaffle_shop__customers",
            ["customer_id"],
            pk="customer_id",
            fqn=["shop", "staging", "c"],
        ),
        "model.shop.stg_jaffle_shop__orders": m(
            "model.shop.stg_jaffle_shop__orders",
            "stg_jaffle_shop__orders",
            ["order_id", "customer_id"],
            pk="order_id",
            fqn=["shop", "staging", "o"],
        ),
        "model.shop.stg_stripe__payments": m(
            "model.shop.stg_stripe__payments",
            "stg_stripe__payments",
            ["payment_id", "order_id"],
            pk="payment_id",
            fqn=["shop", "staging", "p"],
        ),
        "model.shop.dim_customers": m(
            "model.shop.dim_customers", "dim_customers", ["customer_id"], pk="customer_id", fqn=["shop", "marts", "d"]
        ),
        "model.shop.fct_orders": m(
            "model.shop.fct_orders",
            "fct_orders",
            ["order_id", "customer_id"],
            pk="order_id",
            fqn=["shop", "marts", "f"],
        ),
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"metadata": {"project_name": "shop"}, "nodes": nodes, "sources": {}}))
    res = import_dbt(p, infer_fks=True)
    compiled(res)
    assert sorted(res.inferred) == [
        "fct_orders.customer_id -> dim_customers.customer_id",  # fact -> dimension
        "stg_jaffle_shop__orders.customer_id -> stg_jaffle_shop__customers.customer_id",  # same stg_ layer
        "stg_stripe__payments.order_id -> stg_jaffle_shop__orders.order_id",  # stg_ layer + staging folder
    ]


def test_hint_when_columns_unknown(tmp_path, capsys):
    p = tmp_path / "manifest.json"
    m = json.loads((JAFFLE / "manifest.json").read_text())
    for n in m["nodes"].values():
        n["columns"] = {}
    p.write_text(json.dumps(m))
    assert main(["import", "dbt", str(p), "-o", str(tmp_path / "erd")]) == 0
    err = capsys.readouterr().err
    assert "have no known columns" in err and "dbt docs generate" in err
    # with the catalog next to the manifest, no hint
    assert main(["import", "dbt", str(JAFFLE), "-o", str(tmp_path / "erd2")]) == 0
    assert "no known columns" not in capsys.readouterr().err
