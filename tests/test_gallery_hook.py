"""The docs iframes load /demo/skytrax/ and /demo/jaffle/, which the mkdocs hook writes into the site."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "hooks" / "gallery.py").exists() or not (ROOT / "gallery").exists():
    pytest.skip("needs the git checkout's docs hook and gallery/", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("docs_gallery_hook", ROOT / "hooks" / "gallery.py")
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def test_docs_iframes_are_built_with_the_site(tmp_path):
    hook.on_post_build({"site_dir": str(tmp_path)})
    sky = tmp_path / "demo" / "skytrax" / "index.html"
    jaffle = tmp_path / "demo" / "jaffle" / "index.html"
    assert sky.exists() and jaffle.exists()
    model = json.loads(re.search(r'id="qdbd-data">(.*?)</script>', sky.read_text(encoding="utf-8"), re.S).group(1))[
        "model"
    ]
    cust = next(t for t in model["tables"] if t["name"] == "dim_customer")
    assert cust["doc"]
    assert any(c.get("tags") == ["pii"] for c in cust["cols"])
    assert "orders" in jaffle.read_text(encoding="utf-8")
