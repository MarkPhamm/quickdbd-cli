"""Regenerate the gallery card images in docs/assets/img/gallery/<id>.png (1200x630).

    python scripts/gen_thumbnails.py            # every demo
    python scripts/gen_thumbnails.py diff tags  # just these
    python scripts/gen_thumbnails.py hero       # the README hero (docs/assets/img/hero.png)
    python scripts/gen_thumbnails.py path-sql   # the home page's path-to-SQL shot (docs/assets/img/path-sql.png)

Dev-only: needs Playwright (`uv pip install -p .venv playwright`) and drives the system Chrome, so no
browser download. Each demo is opened at its `view` + `shot` URL hash; the screenshot is framed in a card
with the demo's title and description. Commit the PNGs.
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

from build_gallery import ROOT, THUMBS, build, load_catalog
from playwright.sync_api import sync_playwright

from quickdbd_cli.export import font_css
from quickdbd_cli.html import _escape

W, H = 1200, 630
SHOT_W, SHOT_H = 1280, 820
# The home page's "Every relationship is a JOIN" section; hooks/home.py asks join_path for the same two tables.
PATH_SHOT = ("sakila", "t=payment&p=country")
# Hidden in the screenshot: the table list, toolbar, minimap and hint. The details panel and diff bar stay.
CLEAN = ".explorer, .bar, .minimap, .hint { display: none !important; }"

CARD = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@500;600&family=Geist+Mono&display=swap">
<style>{font}
* {{ box-sizing: border-box; margin: 0; }}
body {{ width: {w}px; height: {h}px; overflow: hidden; font-family: Geist, Inter, sans-serif; color: #15181e;
  position: relative; --a: rgba(21, 24, 30, .07); --b: rgba(21, 24, 30, .04); background: #f2f2ee;
  background-image: linear-gradient(var(--a) 1px, #0000 1px), linear-gradient(90deg, var(--a) 1px, #0000 1px),
    linear-gradient(var(--b) 1px, #0000 1px), linear-gradient(90deg, var(--b) 1px, #0000 1px);
  background-size: 120px 120px, 120px 120px, 24px 24px, 24px 24px; background-position: -1px -1px; }}
.text {{ position: absolute; left: 56px; top: 60px; width: 360px; }}
.brand {{ display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 26px; letter-spacing: -.02em;
  margin-bottom: 40px; }}
.brand svg {{ color: #2b5797; }}
.brand span {{ font: 16px "Geist Mono", monospace; color: #646a75; border: 1px solid rgba(21, 24, 30, .24);
  border-radius: 6px; padding: 3px 8px; margin-left: 4px; letter-spacing: 0; }}
h1 {{ font-size: 48px; line-height: 1.04; font-weight: 600; letter-spacing: -.04em; }}
p {{ margin-top: 22px; font-size: 21px; line-height: 1.5; color: #4a505b; }}
.shot {{ position: absolute; left: 460px; top: 56px; width: {sw}px; border-radius: 12px; overflow: hidden;
  border: 1px solid rgba(21, 24, 30, .24); box-shadow: 0 18px 40px -18px rgba(21, 24, 30, .28); background: #fff; }}
.shot img {{ display: block; width: 100%; }}
</style></head><body>
<div class="text">
  <div class="brand"><svg width="30" height="30" viewBox="0 0 24 24"><rect x="2" y="2.5" width="10" height="8" rx="2"
    fill="currentColor"/><rect x="12" y="13.5" width="10" height="8" rx="2" fill="currentColor" opacity=".55"/><path
    d="M7 10.5v3.5a3.5 3.5 0 0 0 3.5 3.5H12" stroke="currentColor" stroke-width="2" fill="none"/></svg>qdbd
    <span>demo</span></div>
  <h1>{title}</h1>
  <p>{description}</p>
</div>
<div class="shot"><img src="data:image/png;base64,{img}"></div>
</body></html>"""


def main(argv: list[str]) -> int:
    catalog = load_catalog()
    wanted = set(argv) or {d.id for d in catalog.demos}
    THUMBS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        out = Path(tmp)
        build(out)
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": SHOT_W, "height": SHOT_H}, device_scale_factor=1)
        card = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for d in catalog.demos:
            if d.id not in wanted:
                continue
            frag = "&".join(x for x in (d.view, d.shot) if x)
            page.goto((out / d.page / "index.html").as_uri() + (f"#{frag}" if frag else ""))
            page.add_style_tag(content=CLEAN)
            page.evaluate("window.dispatchEvent(new Event('resize'))")
            if "z=" not in frag:  # re-fit now that the table list is hidden
                page.evaluate("document.getElementById('zfit').click()")
            page.wait_for_timeout(600)
            img = base64.b64encode(page.screenshot()).decode("ascii")
            card.set_content(
                CARD.format(
                    font=font_css(),
                    w=W,
                    h=H,
                    sw=700,
                    title=_escape(d.title),
                    description=_escape(d.description),
                    img=img,
                )
            )
            card.evaluate("document.fonts.ready.then(() => true)")  # Geist comes from Google Fonts
            dst = THUMBS / f"{d.id}.png"
            card.screenshot(path=str(dst))
            print(f"Wrote {dst.relative_to(THUMBS.parents[3])}")
        hero = catalog.hero
        if hero and "hero" in (set(argv) or {"hero"}):
            page.set_viewport_size({"width": 1440, "height": 860})
            frag = "&".join(x for x in (hero.get("view"), hero.get("shot")) if x)
            page.goto((out / hero["demo"] / "index.html").as_uri() + f"#{frag}")
            page.wait_for_timeout(800)
            dst = ROOT / "docs" / "assets" / "img" / "hero.png"
            page.screenshot(path=str(dst))
            print(f"Wrote {dst.relative_to(ROOT)}")
        if "path-sql" in (set(argv) or {"path-sql"}):
            page.set_viewport_size({"width": 1440, "height": 860})
            page.goto((out / PATH_SHOT[0] / "index.html").as_uri() + f"#{PATH_SHOT[1]}")
            page.wait_for_timeout(800)
            page.get_by_text("Show only this path").click()
            # the home page shows the SQL beside the shot, so the panel goes and the whole path shows
            page.add_style_tag(content=".details, .hint { display: none !important; }")
            page.click("#zfit")
            page.click("#zout")  # fit counts tables only; the payment edge loops out to the right
            page.mouse.move(700, 820)
            page.wait_for_timeout(800)
            dst = ROOT / "docs" / "assets" / "img" / "path-sql.png"
            page.screenshot(path=str(dst))
            print(f"Wrote {dst.relative_to(ROOT)}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
