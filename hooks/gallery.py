"""MkDocs hook: expose gallery/demos.toml to templates, so the home page matches the gallery.

Adds `config.extra.demos` (featured demos, every demo with its table count) and `config.extra.version`.
Table counts come from parsing each demo's schema, without layout, so the docs build stays fast.
"""

import tomllib
from pathlib import Path

from quickdbd_cli import __version__
from quickdbd_cli.dbt import import_dbt
from quickdbd_cli.parser import compile_sources
from quickdbd_cli.project import Project

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "gallery" / "demos.toml"


def _tables(d: dict) -> int:
    if d.get("dbt"):
        res = import_dbt(
            ROOT / d["dbt"],
            packages=d.get("dbt_packages") or None,
            select=d.get("dbt_select") or None,
            split=True,
            infer_fks="--infer-fks" in d.get("build_args", []),
        )
        return len(compile_sources(list(res.files.items())).tables)
    return len(Project.open([ROOT / d["source"]]).compile().tables)


def on_config(config, **kwargs):
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    demos = data.get("demo", [])
    built = {d["id"]: _tables(d) for d in demos if not d.get("of")}
    for d in demos:
        d["href"] = f"demo/{d.get('of') or d['id']}/" + (f"#{d['view']}" if d.get("view") else "")
        d["tables"] = built[d.get("of") or d["id"]]
    config.extra["demos"] = {
        "featured": [d for d in demos if d.get("featured")],
        "all": demos,
        "count": len(demos),
    }
    config.extra["version"] = __version__
    return config
