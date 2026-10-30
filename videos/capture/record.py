"""Record the footage for the qdbd demo video (videos/qdbd-demo).

Real pages built by the real CLI, driven with real mouse and keyboard events, captured over the Chrome DevTools
screencast at 2x and encoded with ffmpeg. Terminal text is the commands' real output, saved verbatim.

    .venv/bin/python videos/capture/record.py            # everything
    .venv/bin/python videos/capture/record.py serve      # one clip

Needs Playwright (dev-only, drives the system Chrome) and ffmpeg. Output goes to videos/capture/out/ (gitignored).
Never point `qdbd serve` at examples/synthetic: dragging rewrites its committed layout file.
"""

import asyncio
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "out"
QDBD = str(ROOT / ".venv" / "bin" / "qdbd")
VIEW = {"width": 1440, "height": 900}
PORT = 8765
CDP_PORT = 9333

# The home tour's cursor and ripple (docs/javascripts/home-tour.js, docs/stylesheets/home.css), plus the Link
# button hidden: the video never shows sharing.
INJECT = """
(() => {
const install = () => {
  const s = document.createElement("style");
  s.textContent = `#xlink { display: none !important; }
    .qv-cursor { position: fixed; left: 0; top: 0; z-index: 2147483647; pointer-events: none;
      transform: translate(-60px, -60px); }
    .qv-ripple { position: fixed; width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%;
      z-index: 2147483646; border: 2px solid #2f5bea; pointer-events: none;
      animation: qv-ripple .5s ease-out forwards; }
    @keyframes qv-ripple { from { transform: scale(.2); opacity: 1; } to { transform: scale(1.3); opacity: 0; } }`;
  document.head.appendChild(s);
  // DOM calls, not innerHTML: VS Code's workbench enforces Trusted Types.
  const ns = "http://www.w3.org/2000/svg", c = document.createElement("div"), svg = document.createElementNS(ns, "svg");
  const path = document.createElementNS(ns, "path");
  c.className = "qv-cursor";
  for (const [k, v] of [["width", "34"], ["height", "34"], ["viewBox", "0 0 24 24"]]) svg.setAttribute(k, v);
  for (const [k, v] of [["d", "M4 2l15 11-7 1.2 4 7.3-2.8 1.5-4-7.4L4 20z"], ["fill", "#111"], ["stroke", "#fff"],
    ["stroke-width", "1.6"], ["stroke-linejoin", "round"]]) path.setAttribute(k, v);
  svg.appendChild(path);
  c.appendChild(svg);
  document.body.appendChild(c);
  addEventListener("mousemove", (e) => {
    c.style.transform = `translate(${e.clientX - 4}px, ${e.clientY - 2}px)`;
  }, true);
  addEventListener("mousedown", (e) => {
    const r = document.createElement("div");
    r.className = "qv-ripple";
    r.style.left = e.clientX + "px";
    r.style.top = e.clientY + "px";
    document.body.appendChild(r);
    setTimeout(() => r.remove(), 600);
  }, true);
};
if (document.readyState === "loading") addEventListener("DOMContentLoaded", install); else install();
})();
"""


def run(args, cwd):
    """Run a real qdbd command; return what a terminal would show."""
    p = subprocess.run([QDBD, *args], cwd=cwd, capture_output=True, text=True, check=True)
    return p.stdout + p.stderr


def prep():
    """Build every page the clips use, and save the terminal text verbatim."""
    shop = OUT / "shop"
    shop.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "shop" / "shop.txt", shop)
    term = OUT / "terminal"
    term.mkdir(exist_ok=True)
    (OUT / "downloads").mkdir(exist_ok=True)
    cmds = {
        "convert": ["convert", "shop.txt", "--to", "dbml", "-o", "shop.dbml"],
        "build": ["build", "shop.dbml", "-o", "shop.html"],
        "export-png": ["export", "shop.txt", "-o", "shop.png", "--scale", "2"],
        "export-svg": ["export", "shop.txt", "-o", "shop.svg"],
        "export-drawio": ["export", "shop.txt", "-o", "shop.drawio"],
    }
    for name, args in cmds.items():
        (term / f"{name}.txt").write_text(f"$ qdbd {' '.join(args)}\n{run(args, shop)}", encoding="utf-8")
    run(["build", str(ROOT / "gallery" / "adventureworks-dw"), "--by-group", "-o", str(OUT / "aw.html")], ROOT)
    run(["build", str(ROOT / "examples" / "synthetic"), "-o", str(OUT / "synthetic.html")], ROOT)
    # --diff-base takes a git ref, so the gallery's diff demo (before.txt -> quickdbd-sample.txt) needs a scratch repo.
    repo = OUT / "diffrepo"
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir()
    shutil.copy(ROOT / "gallery" / "diff" / "before.txt", repo / "schema.txt")
    git = ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.com"]
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "before"]):
        subprocess.run([*git, *args], cwd=repo, check=True)
    shutil.copy(ROOT / "examples" / "quickdbd-sample.txt", repo / "schema.txt")
    run(["build", "schema.txt", "--diff-base", "HEAD", "-o", str(OUT / "diff.html")], repo)
    (term / "diff.md").write_text(run(["diff", "--base", "HEAD", "schema.txt", "--format", "markdown"], repo), "utf-8")


class Recorder:
    """CDP screencast frames with their timestamps, encoded to a constant-30fps MP4."""

    def __init__(self, page, name):
        self.page, self.name = page, name
        self.dir = OUT / "frames" / name
        self.frames = []
        self.done = False
        self.marks = {}

    def mark(self, name):
        """Note when something happens, in clip seconds (marks.json beside the MP4), so the edit can cut on it."""
        self.marks[name] = time.time()

    async def __aenter__(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self.frame)
        view = self.page.viewport_size
        size = {"maxWidth": view["width"] * 2, "maxHeight": view["height"] * 2}
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1, **size})
        return self

    def frame(self, p):
        if self.done:  # a frame can arrive after stopScreencast
            return
        path = self.dir / f"{len(self.frames):05d}.jpg"
        path.write_bytes(base64.b64decode(p["data"]))
        self.frames.append((p["metadata"]["timestamp"], path))
        asyncio.ensure_future(self.ack(p["sessionId"]))

    async def ack(self, sid):
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": sid})
        except Exception:  # the page closed between a frame and its ack
            pass

    async def __aexit__(self, *exc):
        end = time.time()
        self.done = True
        await self.cdp.send("Page.stopScreencast")
        assert self.frames, f"{self.name}: no frames"
        lines = []
        for i, (ts, path) in enumerate(self.frames):
            nxt = self.frames[i + 1][0] if i + 1 < len(self.frames) else end
            lines += [f"file '{path.name}'", f"duration {max(nxt - ts, 0.001):.4f}"]
        lines.append(f"file '{self.frames[-1][1].name}'")  # the concat demuxer drops the last duration otherwise
        (self.dir / "list.txt").write_text("\n".join(lines) + "\n")
        t0 = self.frames[0][0]
        marks = {k: round(v - t0, 2) for k, v in self.marks.items()}
        (OUT / f"{self.name}.marks.json").write_text(json.dumps(marks, indent=1))
        out = OUT / f"{self.name}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "list.txt",
                "-r",
                "30",
                "-fps_mode",
                "cfr",
                "-pix_fmt",
                "yuv420p",
                "-c:v",
                "libx264",
                "-crf",
                "14",
                "-preset",
                "slow",
                "-movflags",
                "+faststart",
                str(out),
            ],
            cwd=self.dir,
            check=True,
        )
        print(f"wrote {out.relative_to(ROOT)} ({len(self.frames)} frames, {end - self.frames[0][0]:.1f}s)")
        shutil.rmtree(self.dir)


class Hand:
    """A mouse that glides like a person's, so the injected cursor moves smoothly."""

    def __init__(self, page):
        self.page, self.x, self.y = page, VIEW["width"] - 80.0, VIEW["height"] - 60.0

    async def to(self, x, y, ms=650):
        n = max(10, ms // 16)
        x0, y0 = self.x, self.y
        for i in range(1, n + 1):
            t = i / n
            e = t * t * (3 - 2 * t)
            await self.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            await asyncio.sleep(ms / 1000 / n)
        self.x, self.y = x, y

    async def to_el(self, sel, ms=650, dx=None, dy=None):
        b = await self.page.locator(sel).first.bounding_box()
        x = b["x"] + (b["width"] / 2 if dx is None else dx)
        await self.to(x, b["y"] + (b["height"] / 2 if dy is None else dy), ms)

    async def click(self, pause=0.12):
        await self.page.mouse.down()
        await asyncio.sleep(pause)
        await self.page.mouse.up()


async def new_page(browser, view=VIEW):
    ctx = await browser.new_context(viewport=view, device_scale_factor=2, color_scheme="light", accept_downloads=True)
    await ctx.add_init_script(INJECT)
    page = await ctx.new_page()
    return page, Hand(page)


async def shop_view(page):
    """Four tables fit at 150%, so the open table list would cover Customer: collapse it to the search box."""
    await page.click("#extoggle")
    await page.click("#zfit")
    await page.wait_for_timeout(600)


async def hook(browser):
    """All 200 tables, from one readable table out to the whole schema.

    A wheel recording zooms in 6% steps and stalls while Chrome repaints 200 tables at 4K, so instead the viewer is
    moved frame by frame through its own #z=&c= hash, one screenshot a frame: the real page on an eased curve at
    exactly 30 fps. The last frame doubles as hook.png, the still the scene settles on."""
    fps, hold, zoom = 30, 0.5, 2.1
    page, _ = await new_page(browser, {"width": 1920, "height": 1080})
    await page.goto((OUT / "synthetic.html").as_uri())
    await page.click("#zfit")
    await page.add_style_tag(content=".explorer, .bar, .minimap, .hint, .qv-cursor { display: none !important; }")
    await page.wait_for_timeout(800)
    # The fit view (zoom and centre, in diagram units) and the centre of the table nearest the middle.
    v = await page.evaluate(
        """() => { const s = window.qdbdViewer.state, w = innerWidth, h = innerHeight;
            let best = null, d = 1e9;
            for (const t of document.querySelectorAll(".t")) {
              const r = t.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2;
              const k = Math.hypot(x - w / 2, y - h / 2);
              if (k < d) { d = k; best = [(x - s.view.x) / s.view.k, (y - s.view.y) / s.view.k]; } }
            return { k: s.view.k, c: [(w / 2 - s.view.x) / s.view.k, (h / 2 - s.view.y) / s.view.k], t: best }; }"""
    )
    k0, k1 = 1.6, v["k"] * 1.2  # readable; then a little inside fit, so the settled plate is full
    frames = OUT / "frames" / "hook"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir(parents=True)
    n = round((hold + zoom) * fps)
    for i in range(n):
        u = min(1.0, max(0.0, (i / fps - hold) / zoom))
        e = u * u * (3 - 2 * u)
        k = math.exp(math.log(k0) + (math.log(k1) - math.log(k0)) * e)  # even speed in log zoom
        cx, cy = (v["t"][j] + (v["c"][j] - v["t"][j]) * e for j in (0, 1))
        await page.evaluate("(h) => { location.hash = h; }", f"z={k:.5f}&c={cx:.1f},{cy:.1f}")
        await page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        await page.screenshot(path=str(frames / f"{i:05d}.jpg"), type="jpeg", quality=92)
    shutil.copy(frames / f"{n - 1:05d}.jpg", OUT / "hook-end.jpg")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(frames / "%05d.jpg"),
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-crf",
            "14",
            "-preset",
            "slow",
            "-movflags",
            "+faststart",
            str(OUT / "hook.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "hook-end.jpg"), str(OUT / "hook.png")], check=True
    )
    shutil.rmtree(frames)
    print(f"wrote videos/capture/out/hook.mp4 ({n} frames, {n / fps:.1f}s) and hook.png")


async def opened(browser):
    """The shop diagram just opened: hover lights each table's relationships."""
    page, hand = await new_page(browser)
    await page.goto((OUT / "shop" / "shop.html").as_uri())
    await shop_view(page)
    async with Recorder(page, "open") as rec:
        await asyncio.sleep(0.4)
        for t in ("Order", "OrderLine", "Product"):
            await hand.to_el(f'.t[data-id="{t}"]', 700, dy=14)
            rec.mark(f"hover-{t}")
            await asyncio.sleep(1.1)
        await asyncio.sleep(0.3)


async def explore(browser):
    """AdventureWorks DW: search, select (neighbours stay lit), hover a relationship, read the details."""
    page, hand = await new_page(browser)
    await page.goto((OUT / "aw.html").as_uri() + "#z=0.6&c=900,1000")
    await page.wait_for_timeout(900)
    async with Recorder(page, "explore") as rec:
        await asyncio.sleep(0.5)
        await hand.to_el("#q", 600, dx=60)
        await page.keyboard.press("/")
        rec.mark("type")
        await asyncio.sleep(0.2)
        await page.keyboard.type("FactInternetS", delay=95)
        await asyncio.sleep(0.5)
        await hand.to_el('.ti[data-id="FactInternetSales"]', 600, dx=70)
        rec.mark("select")
        await hand.click()
        await asyncio.sleep(1.6)
        k = "FactInternetSales|CustomerKey|DimCustomer|CustomerKey"
        pt = await page.evaluate(
            """(k) => { const p = document.querySelector('.hit path[data-k="' + k + '"]');
                const m = p.getPointAtLength(p.getTotalLength() * 0.5), c = p.getScreenCTM();
                return {x: m.x * c.a + c.e, y: m.y * c.d + c.f}; }""",
            k,
        )
        await hand.to(pt["x"], pt["y"], 800)
        rec.mark("line")
        await asyncio.sleep(1.8)
        await hand.to_el("#details", 700, dy=260)
        rec.mark("details")
        await asyncio.sleep(1.4)


async def serve(browser):
    """qdbd serve: type a new table in the editor pane; autosave; it lands next to Product; drag it."""
    work = OUT / "serve"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    shutil.copy(HERE / "shop" / "shop.txt", work)
    proc = subprocess.Popen(
        [QDBD, "serve", "shop.txt", "--port", str(PORT), "--no-open"],
        cwd=work,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        first = proc.stdout.readline()
        (OUT / "terminal" / "serve.txt").write_text(f"$ qdbd serve shop.txt\n{first.split('  (layout')[0]}\n", "utf-8")
        page, hand = await new_page(browser)
        await page.goto(f"http://127.0.0.1:{PORT}/")
        await page.wait_for_selector(".CodeMirror")
        await page.wait_for_timeout(1200)
        await page.evaluate(
            "() => { const cm = document.querySelector('.CodeMirror').CodeMirror; "
            "cm.focus(); cm.setCursor(cm.lineCount(), 0); }"
        )
        async with Recorder(page, "serve") as rec:
            await asyncio.sleep(0.4)
            await hand.to(200, 470, 600)
            rec.mark("type")
            await page.keyboard.type(
                "\nReview\n-\nReviewId PK int\nProductId int FK >- Product.ProductId\nStars int", delay=55
            )
            rec.mark("typed")
            await page.wait_for_selector('.t[data-id="Review"]', timeout=10000)
            rec.mark("drawn")
            await asyncio.sleep(1.2)
            b = await page.locator('.t[data-id="Review"]').bounding_box()
            await hand.to(b["x"] + 60, b["y"] + 14, 700)
            await page.mouse.down()
            rec.mark("drag")
            await hand.to(b["x"] - 240, b["y"] + 330, 1000)  # into the empty space under OrderLine
            await page.mouse.up()
            await asyncio.sleep(1.2)
    finally:
        proc.terminate()
        proc.wait()


async def exports(browser):
    """The toolbar's SVG, PNG and draw.io buttons, clicked for real."""
    page, hand = await new_page(browser)
    await page.goto((OUT / "shop" / "shop.html").as_uri())
    await shop_view(page)
    async with Recorder(page, "exports") as rec:
        await asyncio.sleep(0.3)
        for b in ("#xsvg", "#xpng", "#xdrawio"):
            await hand.to_el(b, 450)
            rec.mark(b[1:])
            async with page.expect_download() as dl:
                await hand.click()
            await (await dl.value).save_as(OUT / "downloads" / (await dl.value).suggested_filename)
            await asyncio.sleep(0.35)
        await asyncio.sleep(0.4)


async def diff(browser):
    """Still: what a branch changed, coloured in."""
    page, _ = await new_page(browser)
    await page.goto((OUT / "diff.html").as_uri())
    await page.wait_for_timeout(600)
    await page.click("#extoggle")
    await page.add_style_tag(content=".qv-cursor { display: none !important; }")
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(OUT / "diff.png"))
    print("wrote videos/capture/out/diff.png")


VSCODE_APP = ROOT / "vscode" / ".vscode-test" / "vscode-darwin-arm64-1.143.1" / "Visual Studio Code.app"
VSCODE_SETTINGS = {
    "workbench.colorTheme": "Default Dark Modern",
    "window.zoomLevel": 0,
    "editor.fontSize": 16,
    "editor.minimap.enabled": False,
    "editor.stickyScroll.enabled": False,
    "editor.quickSuggestions": {"other": False, "comments": False, "strings": False},
    "editor.suggestOnTriggerCharacters": False,
    "editor.wordBasedSuggestions": "off",
    "editor.hover.delay": 250,
    "editor.lightbulb.enabled": "off",
    "workbench.startupEditor": "none",
    "workbench.tips.enabled": False,
    "workbench.activityBar.location": "hidden",
    "workbench.secondarySideBar.defaultVisibility": "hidden",
    "workbench.layoutControl.enabled": False,
    "window.commandCenter": False,
    "chat.disableAIFeatures": True,
    "security.workspace.trust.enabled": False,
    "update.mode": "none",
    "telemetry.telemetryLevel": "off",
    "extensions.ignoreRecommendations": True,
    "workbench.enableExperiments": False,
    "git.enabled": False,
    "window.restoreWindows": "none",
}


def line(page, text):
    """The editor line whose whole text is `text`."""
    words = r"\s+".join(map(re.escape, text.split()))  # Monaco renders spaces as no-break spaces; JS \s matches them
    return page.locator(".view-line").filter(has_text=re.compile(rf"^\s*{words}\s*$")).first


async def vscode(browser):
    """Real VS Code (the integration tests' download) with this checkout's extension: the diagram opens beside the file,
    a typo gets QuickDBD's own error, the fix is saved and drawn, and the diagram follows the cursor."""
    base = OUT / "vscode"
    shutil.rmtree(base, ignore_errors=True)
    ws = base / "shop"
    (ws / ".vscode").mkdir(parents=True)
    shutil.copy(HERE / "shop" / "shop.txt", ws)
    (ws / ".vscode" / "settings.json").write_text(json.dumps({"quickdbd.qdbdPath": QDBD}))
    (base / "user-data" / "User").mkdir(parents=True)
    (base / "user-data" / "User" / "settings.json").write_text(json.dumps(VSCODE_SETTINGS))
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}  # set inside VS Code terminals
    args = [
        str(VSCODE_APP / "Contents" / "MacOS" / "Code"),
        str(ws),
        str(ws / "shop.txt"),
        "--new-window",
        f"--extensionDevelopmentPath={ROOT / 'vscode'}",
        "--disable-workspace-trust",
        f"--user-data-dir={base / 'user-data'}",
        f"--extensions-dir={base / 'extensions'}",
        "--skip-welcome",
        "--skip-release-notes",
        f"--remote-debugging-port={CDP_PORT}",
        "--force-device-scale-factor=2",
    ]
    proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{CDP_PORT}"
        for _ in range(60):
            try:
                urllib.request.urlopen(url + "/json/version", timeout=1)
                break
            except OSError:
                await asyncio.sleep(0.5)
        vs = await browser.browser_type.connect_over_cdp(url)
        page = None
        while page is None:
            page = next((pg for c in vs.contexts for pg in c.pages if "workbench" in pg.url), None)
            await asyncio.sleep(0.5)
        await page.wait_for_selector(".monaco-editor .view-line", timeout=60000)
        await page.set_viewport_size(VIEW)  # Electron has no Browser.setWindowBounds; emulate the size instead
        await page.evaluate(INJECT)
        await page.keyboard.press("Meta+B")  # hide the Explorer: editor and diagram side by side
        await asyncio.sleep(4)  # the extension activates and checks the file
        await page.keyboard.press("F1")
        await page.keyboard.type("Open Diagram to the Side", delay=20)
        await asyncio.sleep(0.6)
        await page.keyboard.press("Enter")
        await asyncio.sleep(6)  # qdbd serve --embed starts; the diagram appears beside the file
        # The schema text is narrow: give the diagram more of the width.
        sash = await page.locator(".part.editor .monaco-sash.vertical").first.bounding_box()
        await page.mouse.move(sash["x"] + 2, sash["y"] + sash["height"] / 2)
        await page.mouse.down()
        await page.mouse.move(sash["x"] - 150, sash["y"] + sash["height"] / 2, steps=8)
        await page.mouse.up()
        await asyncio.sleep(1.5)
        hand = Hand(page)
        async with Recorder(page, "vscode") as rec:
            await asyncio.sleep(0.6)
            for t in ("Customer", "Product"):
                b = await line(page, t).bounding_box()
                await hand.to(b["x"] + 60, b["y"] + b["height"] / 2, 700)
                rec.mark(f"follow-{t}")
                await hand.click()
                await asyncio.sleep(1.8)  # the diagram follows the cursor to that table
            b = await line(page, "Total money").bounding_box()
            await hand.to(b["x"] + 240, b["y"] + b["height"] / 2, 700)
            await hand.click()
            await page.keyboard.press("End")
            await page.keyboard.press("Enter")
            rec.mark("type")
            await page.keyboard.type("ProductId int FK >- Prodcut.ProductId", delay=55)
            await page.locator(".squiggly-error").first.wait_for(timeout=15000)
            await asyncio.sleep(0.4)
            rec.mark("squiggle")
            await hand.to_el(".squiggly-error", 600)
            rec.mark("hover")
            await asyncio.sleep(2.6)  # the hover shows QuickDBD's own message
            for _ in range(len(".ProductId")):
                await page.keyboard.press("ArrowLeft")
                await asyncio.sleep(0.03)
            await page.keyboard.press("Alt+Shift+ArrowLeft")
            await asyncio.sleep(0.3)
            rec.mark("fix")
            await page.keyboard.type("Product", delay=70)
            await asyncio.sleep(2.0)  # checked as you type, unsaved: the error clears
        await vs.close()
    finally:
        proc.terminate()
        proc.wait(timeout=15)


CLIPS = {
    "hook": hook,
    "open": opened,
    "explore": explore,
    "serve": serve,
    "exports": exports,
    "diff": diff,
    "vscode": vscode,
}


async def main(names):
    prep()
    async with async_playwright() as p:
        # The screencast sends frames at the window's real scale, not the emulated one: force a 2x window.
        browser = await p.chromium.launch(channel="chrome", args=["--force-device-scale-factor=2"])
        for name in names or CLIPS:
            await CLIPS[name](browser)
        await browser.close()
    # The video project reads its footage from assets/footage (gitignored: rebuild it with this script).
    footage = ROOT / "videos" / "qdbd-demo" / "assets" / "footage"
    footage.mkdir(parents=True, exist_ok=True)
    for f in [*OUT.glob("*.mp4"), *OUT.glob("*.marks.json"), OUT / "hook.png", OUT / "diff.png"]:
        if f.exists() and f.name != "hook-in.mp4":
            shutil.copy(f, footage)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
