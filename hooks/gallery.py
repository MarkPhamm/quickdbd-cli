"""MkDocs hook: expose gallery/demos.toml to templates, so the home page's demo grid matches the gallery, and the
package version from pyproject.toml, for the header's version pill.

The dbt and jaffle docs pages embed /demo/skytrax/ and /demo/jaffle/. CI builds the whole gallery after mkdocs, so
those iframes 404 on `mkdocs serve` and on a plain `mkdocs build`. This writes the two pages into the site.
"""

import contextlib
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "gallery" / "demos.toml"
# Iframes in docs/dbt.md and docs/example/index.md. Keep these in step with those src attributes.
EMBEDDED = ("skytrax", "jaffle")

_pages: dict[str, str] | None = None  # mkdocs serve rebuilds on every edit; these pages don't change with the docs


def on_config(config, **kwargs):
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    demos = data.get("demo", [])
    for d in demos:
        d["href"] = f"demo/{d.get('of') or d['id']}/" + (f"#{d['view']}" if d.get("view") else "")
    config.extra["demos"] = {"featured": [d for d in demos if d.get("featured")], "count": len(demos)}
    config.extra["version"] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    return config


def embedded_pages() -> dict[str, str]:
    """HTML for the demos the docs embed, laid out once per process."""
    global _pages
    if _pages is None:
        scripts = str(ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import build_gallery

        catalog = build_gallery.load_catalog()
        pages = {}
        with contextlib.chdir(ROOT):  # paths shown in the diagram are relative to the repo
            for demo_id in EMBEDDED:
                page, _model = build_gallery.build_demo(catalog.get(demo_id))
                pages[demo_id] = page
        _pages = pages
    return _pages


def on_post_build(config, **kwargs):
    out = Path(config["site_dir"]) / "demo"
    for demo_id, page in embedded_pages().items():
        dest = out / demo_id / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")
