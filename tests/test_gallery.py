"""The demo gallery (gallery/demos.toml -> scripts/build_gallery.py)."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_gallery  # noqa: E402


def _data(index: Path) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', index.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))


def _model(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="qdbd-data">(.*?)</script>', text, re.S)
    return json.loads(m.group(1))["model"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("gallery")
    build_gallery.build(out)
    return out


def test_catalog_is_valid_and_every_demo_has_a_thumbnail():
    catalog = build_gallery.load_catalog()
    assert catalog.demos
    for d in catalog.demos:
        assert (build_gallery.THUMBS / f"{d.id}.png").exists(), f"run scripts/gen_thumbnails.py {d.id}"
    assert any(d.featured for d in catalog.demos)


def test_catalog_errors_are_reported(tmp_path):
    bad = tmp_path / "demos.toml"
    bad.write_text(
        '[[group]]\nid = "g"\ntitle = "G"\ndescription = ""\n'
        '[[demo]]\nid = "a"\ngroup = "nope"\ntitle = "A"\ndescription = ""\nsource = "missing/"\n'
        '[[demo]]\nid = "a"\ngroup = "g"\ntitle = "B"\ndescription = ""\nof = "zzz"\nbuild_args = ["--rm"]\n',
        encoding="utf-8",
    )
    with pytest.raises(build_gallery.CatalogError) as e:
        build_gallery.load_catalog(bad)
    msg = str(e.value)
    for part in ("duplicate demo id 'a'", "unknown group 'nope'", "source path not found", "'of' must name", "--rm"):
        assert part in msg


def test_build_writes_gallery_and_one_page_per_built_demo(built):
    catalog = build_gallery.load_catalog()
    for d in catalog.demos:
        page = built / d.page / "index.html"
        assert page.exists()
        assert "&larr; All demos" in page.read_text(encoding="utf-8")
        assert (built / "thumbs" / f"{d.id}.png").exists()
    data = _data(built / "index.html")
    assert [c["id"] for c in data["demos"]] == [d.id for d in catalog.demos]
    cards = {c["id"]: c for c in data["demos"]}
    assert cards["synthetic"]["tables"] == 200
    assert cards["path"]["href"].startswith("synthetic/#") and cards["path"]["tables"] == 200
    assert cards["jaffle"]["kind"] == "dbt"
    assert "__DATA__" not in (built / "index.html").read_text(encoding="utf-8")


def test_feature_demos(built):
    diff = _model(built / "diff" / "index.html")
    assert diff["diff"]["added"] == 2 and diff["diff"]["changed"] == 3
    assert _model(built / "regions" / "index.html").get("regions")
    tags = _model(built / "tags" / "index.html")
    assert {"dim", "fact", "staging", "gold"} <= {t["name"] for t in tags["tags"]}


def test_build_is_deterministic(built, tmp_path):
    build_gallery.build(tmp_path)
    for p in sorted(built.rglob("*.html")):
        assert p.read_bytes() == (tmp_path / p.relative_to(built)).read_bytes(), p
