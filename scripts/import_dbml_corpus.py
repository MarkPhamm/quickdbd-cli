"""Import the DBML acceptance corpus from @dbml/parse's snapshot tests into tests/fixtures/dbml-ref/.

Usage: python scripts/import_dbml_corpus.py PATH/TO/holistics-dbml [--out tests/fixtures/dbml-ref]

Copies each `<stage>/input/<name>.in.dbml` to `<out>/<stage>/<name>.dbml` and writes `<name>.json`, a compact
form of the reference result: the error lines, or (for the interpreter stage) the tables, refs and groups the
reference parser produced. Only the interpreter stage's clean cases are known-valid DBML; the other stages are
kept for their errors. The corpus is Apache-2.0 (see the LICENSE copied next to it).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

STAGES = ("interpreter", "validator", "binder", "parser")
SNAPSHOTS = "packages/dbml-parse/__tests__/snapshots"


def _line(err: dict) -> int | None:
    ctx = (err.get("node") or err.get("token") or {}).get("context") or {}
    m = re.search(r"\[L(\d+):C\d+", ctx.get("id", ""))
    return int(m.group(1)) + 1 if m else None


def _field(f: dict) -> dict:
    out = {"name": f["name"], "type": f["type"]["type_name"]}
    if f["type"].get("schemaName"):
        out["type_schema"] = f["type"]["schemaName"]
    for k in ("pk", "unique", "not_null", "increment"):
        if k in f:
            out[k] = f[k]
    if f.get("note"):
        out["note"] = f["note"]["value"]
    if f.get("dbdefault"):
        out["default"] = {"type": f["dbdefault"]["type"], "value": f["dbdefault"]["value"]}
    if f.get("inline_refs"):
        out["inline_refs"] = [
            {
                "table": r["tableName"],
                "schema": r.get("schemaName"),
                "fields": r["fieldNames"],
                "relation": r["relation"],
            }
            for r in f["inline_refs"]
        ]
    return out


def _indexes(t: dict) -> list[dict]:
    return [
        {
            "columns": [c["value"] for c in i["columns"] if c["type"] == "column"],
            "pk": i.get("pk", False),
            "unique": i.get("unique", False),
            "expressions": sum(c["type"] != "column" for c in i["columns"]),
        }
        for i in t.get("indexes", [])
    ]


def _database(db: dict) -> dict:
    tables = []
    for t in db.get("tables", []):
        table = {
            "name": t["name"],
            "schema": t.get("schemaName"),
            "fields": [_field(f) for f in t["fields"]],
            "indexes": _indexes(t),
            "partials": [{"name": p["name"], "order": p["order"]} for p in t.get("partials", [])],
        }
        for k in ("alias", "headerColor"):
            if t.get(k):
                table[k] = t[k]
        if t.get("note"):
            table["note"] = t["note"]["value"]
        tables.append(table)
    partials = [
        {
            "name": p["name"],
            "fields": [_field(f) for f in p.get("fields", [])],
            "indexes": _indexes(p),
            **({"headerColor": p["headerColor"]} if p.get("headerColor") else {}),
            **({"note": p["note"]["value"]} if p.get("note") else {}),
        }
        for p in db.get("tablePartials", [])
    ]
    refs = [
        {
            "endpoints": [
                {
                    "table": e["tableName"],
                    "schema": e.get("schemaName"),
                    "fields": e["fieldNames"],
                    "relation": e["relation"],
                }
                for e in r["endpoints"]
            ]
        }
        for r in db.get("refs", [])
    ]
    groups = [
        {"name": g["name"], "tables": [{"name": x["name"], "schema": x.get("schemaName")} for x in g.get("tables", [])]}
        for g in db.get("tableGroups", [])
    ]
    return {
        "tables": tables,
        "tablePartials": partials,
        "refs": refs,
        "tableGroups": groups,
        "enums": [e["name"] for e in db.get("enums", [])],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--out", default="tests/fixtures/dbml-ref")
    args = ap.parse_args()
    src, out = Path(args.repo) / SNAPSHOTS, Path(args.out)
    for stage in STAGES:
        (out / stage).mkdir(parents=True, exist_ok=True)
        for inp in sorted((src / stage / "input").glob("*.in.dbml")):
            name = inp.name[: -len(".in.dbml")]
            res = json.loads((src / stage / "output" / f"{name}.out.json").read_text())
            errors = sorted(
                {(_line(e), e.get("code"), e.get("diagnostic")) for e in res.get("errors") or []},
                key=lambda e: (e[0] or 0, e[1] or ""),
            )
            if stage != "interpreter" and not errors:
                continue  # not known to be valid, and no error to check
            expected: dict = {"errors": [{"line": ln, "code": c, "message": m} for ln, c, m in errors]}
            if not errors:
                expected["database"] = _database(res["database"])
            shutil.copyfile(inp, out / stage / f"{name}.dbml")
            (out / stage / f"{name}.json").write_text(json.dumps(expected, indent=1, sort_keys=True) + "\n")
    shutil.copyfile(Path(args.repo) / "LICENSE", out / "LICENSE")


if __name__ == "__main__":
    main()
