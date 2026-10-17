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
