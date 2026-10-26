"""MkDocs hook: expose gallery/demos.toml to templates, so the home page's demo grid matches the gallery, and the
package version from pyproject.toml, for the header's version pill."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "gallery" / "demos.toml"


def on_config(config, **kwargs):
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    demos = data.get("demo", [])
    for d in demos:
        d["href"] = f"demo/{d.get('of') or d['id']}/" + (f"#{d['view']}" if d.get("view") else "")
    config.extra["demos"] = {"featured": [d for d in demos if d.get("featured")], "count": len(demos)}
    config.extra["version"] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    return config
