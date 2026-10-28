# UI upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relationship lines that light up (with labels, flowing dashes and a relationship card) and faster drags in every qdbd viewer, plus a landing page with motion in every section, a redesigned hero and a scripted live demo.

**Architecture:**
- **Viewer:** pure helpers (label spots, card text, single-relationship JOIN) go in `render.js` and are tested from Python through `jsrt`. `viewer.js` adds a hit layer, lit classes, an overlay group (labels and dashes) and the card. Drags redraw only the touching edges.
- **Landing page:** an MkDocs hook renders the mini diagram from the snippet in `overrides/home.html` and builds the AdventureWorks tour page into the site. Plain JS files loaded on every page (no-ops off the home page) add the motion.

**Tech Stack:** vanilla JS/CSS, Python 3.11+, mini-racer (`jsrt`), MkDocs Material hooks, Playwright for manual checks only.

**Spec:** `docs/superpowers/specs/2026-10-28-ui-upgrade-design.md`. Mockups: `docs/superpowers/specs/assets/2026-10-28-ui-upgrade/`. Read both before each task.

## Global Constraints

- **Exports unchanged:** PNG, SVG and draw.io never contain lit state, labels, dashes or the card. Default renders stay byte-identical, and `test_build_is_deterministic…` must keep passing.
- **No network:** built qdbd pages load nothing from the network. No new runtime dependencies, no npm build.
- **Reduced motion:** in the viewer, lines still light and labels still show, but dashes don't move and glides are instant. On the landing page, everything shows in its final state.
- **Landing-page layout:** nothing crosses the page margins. No sideways scroll at 390px wide. Right edges line up at 1280px and 1512px.
- **Lit colours:** light `--lit: #4361ee`, `--lit-deep: #2a3fb8`; dark `--lit: #8aa0ff`, `--lit-deep: #c3ceff`.
- **Lit line style:** stroke about 2.2px. Dashes `stroke-dasharray: 4 18`, 1.1s loop. Hit target 14px wide. Dimming 0.18 for tables, 0.07 for lines.
- **Card labels:** `one` → `1`, `zeroOne` → `0..1`, `many` → `*`, `zeroMany` → `0..*`. Sentence words: `one`, `zero or one`, `many`, `zero or many`.
- **Python conventions:** imports at module top. Ruff check plus format.
- **Writing rules:** no emoji or icons anywhere. Commits and the PR carry no AI attribution.
- **Off limits:** `examples/synthetic/qdbd.layout.json` and other local layout files are never committed.

## Review Focus

1. **Self-referencing relationships** (`a.t === b.t`): both ends sit on the right side. Labels must not overlap the line, and the card must still read correctly. Test in Task 1.
2. **Composite and table-level relationships:** the card JOIN must match `qdbd path` (`ON a AND b`, and `ON ...  -- table-level relationship...`). Test in Task 1.
3. **A locked line that disappears** (filter change, mode change, `qdbdViewer.setData` live reload in serve) must clear silently, never throw. Check in Task 2.
4. **Hover cost on 1000-table diagrams:** hover must not rebuild every hit path. Build the hit layer once per render, and on hover redecorate only the lit edges. Check in Task 2.
5. **Tour page missing** (`mkdocs serve` without the hook output, or the iframe 404s): the live demo falls back to the still image instead of a broken frame. Check in Task 8.

---

### Task 1: render.js helpers for labels and the relationship card

**Files:**
- Modify: `src/quickdbd_cli/assets/render.js` (near `edgeGeom` and `pathSql`, and in the exports at the bottom)
- Test: `tests/test_render.py`

**Interfaces:**
- Produces:
  - `qdbd.edgeLabels(model, pos, mode, rel)` → `[{x, y, anchor, text}, {x, y, anchor, text}]` for the a end then the b end, or `null` when either table has no position.
  - `qdbd.relCard(model, i)` → `{from: "Order.CustomerId", to: "Customer.CustomerId", cardFrom: "*", cardTo: "1", sentence: "Each Customer row has many Order rows", sql: "FROM ...\nJOIN ..."}`.
    - `from` is the child (FK / many) side. Parent and child are picked the way `viewer.js` `showDetails` picks them.
    - The SQL comes from `pathSql` with one step and `stepPairs`.
    - A composite ref shows `Order.(a, b)`. A table-level side shows just the table name.
  - Globals `qdbdEdgeLabels` and `qdbdRelCard`, for Python.

- [ ] **Step 1: Write the failing tests** in `tests/test_render.py`, using `runtime().load("render.js")` and `rt.call(...)` like `tests/test_path.py`:
  - `test_rel_card_simple`: on the QuickDBD Order/Customer snippet from `docs/superpowers/specs/assets/2026-10-28-ui-upgrade/snippet.txt`:
    - `cardFrom == "*"`, `cardTo == "1"`;
    - `sentence == "Each Customer row has many Order rows"`;
    - `sql == "FROM \"Order\"\nJOIN Customer ON Customer.CustomerId = \"Order\".CustomerId"` (`Order` is reserved).
  - `test_rel_card_composite`: on the DBML composite schema from `test_path.py`, `sql == "FROM t\nJOIN v ON v.a = t.a AND v.b = t.b"` and `from == "t.(a, b)"`.
  - `test_rel_card_table_level`: on the `rel >- B` schema from `test_parser.py:240`:
    - `sql` ends with `-- table-level relationship: join columns not specified`;
    - `from == "A"`.
  - `test_edge_labels_sides`: Customer at `[0,10]`, Order at `[300,0]`:
    - the Order end label has `anchor == "end"` and `x < 300`;
    - the Customer end label has `anchor == "start"` and `x > 189`;
    - texts are `["*", "1"]`.
  - `test_edge_labels_self_ref`: a table with an FK to itself. Both labels have `anchor == "start"` and sit right of the table.
  - `test_edge_labels_missing_position`: returns `None` when one table has no position.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_render.py -q`. Expected: the new tests FAIL (`qdbdRelCard is not defined`).
- [ ] **Step 3: Implement `edgeLabels` and `relCard` in `render.js`.**
  - Labels sit 8px beyond each end along its direction (`da`/`db` from `edgeGeom`), 9px above the line.
  - `anchor` is `"start"` when the direction is `+1`, else `"end"`.
  - Export both on `root.qdbd` and as `root.qdbdEdgeLabels` / `root.qdbdRelCard`.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_render.py tests/test_path.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "render.js: edge labels and relationship card text"`.

### Task 2: Lit relationships in the viewer

**Files:**
- Modify: `src/quickdbd_cli/assets/viewer.js`
- Modify: `src/quickdbd_cli/assets/style.css`
- Test: manual (Playwright), plus the contract test in Task 3.

**Interfaces:**
- Consumes: `Q.edgeLabels` (Task 1).
- Produces:
  - **State:** `S.edge` (locked line key or null) and `S.hover` (`{t: id}` or `{e: key}` or null).
  - **Key format:** `a|ac|b|bc`, the same as the `.e` data attributes.
  - **DOM:**
    - `<g class="hit">` with one `<path data-k>` per edge, before `.tables`.
    - `<g class="fx">` holding `.lbl` texts and `.flow` paths, before `.tables`.
    - Classes `.lit` on `.e`/`.r`, `.on` on `.t`, `efocus` on `#canvas`.
  - **Function:** `light()` recomputes lit classes and redraws `.fx` for lit edges only.

- [ ] **Step 1: Build the hit layer in `render()`** from the `.ep` path data, once per render, and rebuild it in `renderEdges()`.
- [ ] **Step 2: Add the light rules.**
  - An edge is lit when its key is `S.edge`, or it touches `S.hover.t`, or its key is `S.hover.e`, or it is not dimmed under the current table focus, or it has row-hover `.hl`.
  - Path (`.ph`) edges get an amber `.flow`.
  - Table click clears `S.edge`. A line click (pointerup without movement on a `.hit path`) sets `S.edge` and clears `S.focus`.
  - Esc and an empty-canvas click clear both.
  - `applyFocus`, `select`, `applyFilter`, `setMode` and `qdbdViewer.setData` end by calling `light()`. A locked key with no matching `.e` resets to null.
- [ ] **Step 3: Add the CSS** from `viewer-lit-relationships.html`:
  - `.e.lit` stroke, `.efocus` dimming, `.r.lit .rb`;
  - `.fx .lbl` with a `var(--bg)` halo, `.fx .flow` with the `flow` keyframes, `.hit path` (14px transparent stroke, `pointer-events: stroke`, `cursor: pointer`);
  - `.t:hover .tb` drop shadow;
  - `@media (prefers-reduced-motion: reduce) { .fx .flow { animation: none } }`;
  - the `--lit` / `--lit-deep` tokens in both themes.
- [ ] **Step 4: Make synthetic events safe.** Wrap `svg.setPointerCapture` and `mini.setPointerCapture` in try/catch.
- [ ] **Step 5: Browser check** with Playwright and system Chrome on `qdbd build examples/synthetic -o /tmp/d.html` and on a dark-theme load:
  - Hover a table: its lines light up with labels.
  - Click a line: it locks, other tables dim.
  - Esc clears.
  - A filter change while a line is locked raises no console error.
  - No exception after `qdbdViewer.setData(model, pos)`.
- [ ] **Step 6: Run** `.venv/bin/pytest -q`. Expected: PASS, including determinism.
- [ ] **Step 7: Commit** `git commit -m "viewer: light relationship lines with labels and flowing dashes"`.

### Task 3: Relationship card, copy fallback, tour contract test

**Files:**
- Modify: `src/quickdbd_cli/html.py` (add `<div class="rcard" id="rcard" role="dialog"></div>` to `BODY`, next to `#tip`)
- Modify: `src/quickdbd_cli/assets/viewer.js`, `src/quickdbd_cli/assets/style.css`
- Create: `tests/test_viewer_contract.py`

**Interfaces:**
- Consumes: `Q.relCard` (Task 1), `S.edge` (Task 2).
- Produces:
  - `#rcard` containing `.rt` (title), `.rk` (sentence), `pre`, `a#rcopy` ("Copy JOIN") and `a#rboth` ("Show both tables").
  - `copyText(text, label)` in `viewer.js`, used by Copy JOIN, Copy SQL and Link.

- [ ] **Step 1: Write the failing test** `tests/test_viewer_contract.py::test_tour_contract`. Build `examples/quickdbd-sample.txt` with `Project.build`, then assert:
  - the page contains `id="q"`, `id="filter"`, `id="zfit"` and `id="rcard"`;
  - `viewer.js` contains `id="pathto"`, `id="pathsql"`, `id="rcopy"` and `class="hit"`.
  - Docstring: these are what the landing-page tour drives.
- [ ] **Step 2: Run it.** Expected: FAIL on `rcard`.
- [ ] **Step 3: Implement the card.**
  - It opens at the click point, clamped inside `#stage`, with a 160ms scale-and-fade.
  - It closes on Esc, on an outside click, and on selection change.
  - Show both tables calls `applyFilter` with the two names, using the same `?` escaping as `pathonly`.
  - `copyText` tries `navigator.clipboard` when `isSecureContext`. Otherwise, or on rejection, it selects the `pre` (Copy JOIN / Copy SQL) and shows the toast `"Press Ctrl/Cmd+C"`. Link keeps its `prompt` fallback.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_viewer_contract.py -q`. Expected: PASS.
- [ ] **Step 5: Browser check:** click a line; the card shows the title, sentence and SQL; Copy JOIN shows "JOIN copied"; Show both tables leaves 2 tables. Check the embed fallback by loading `qdbd serve --embed` in an iframe without `clipboard-write`.
- [ ] **Step 6: Commit** `git commit -m "viewer: relationship card with Copy JOIN"`.

### Task 4: Faster drags

**Files:**
- Modify: `src/quickdbd_cli/assets/viewer.js` (pointer handlers, `renderEdges`)

**Interfaces:**
- Consumes: `Q.renderEdges(model, pos, mode, geo)` (existing), and `light()` from Task 2 for the dragged table's edges.

- [ ] **Step 1: Measure the baseline.** A Playwright script drags a table on `examples/synthetic` for 60 frames and records the mean `requestAnimationFrame` delta. Note the number.
- [ ] **Step 2: Redraw only the touching edges.**
  - At drag start, cache `geo = Q.geometry(S.vm, S.mode)`, the rels touching the table, and their `.e` elements.
  - Each frame, render only those rels via `Q.renderEdges({style, tables: S.vm.tables, rels: touching}, S.pos, S.mode, geo)`, swap the elements, and copy their state classes.
  - Update their hit paths and `.fx` items.
  - No `applyFocus` per frame.
  - On drop, run the full `renderEdges()` once.
- [ ] **Step 3: Measure again.** Expected: a mean frame delta of 20ms or less on `examples/synthetic`, and lower than the baseline.
- [ ] **Step 4: Run** `.venv/bin/pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "viewer: redraw only the dragged table's edges"`.

### Task 5: Glides, details slide-in, docs note

**Files:**
- Modify: `src/quickdbd_cli/assets/viewer.js` (`fit`, `centerOn`, zoom buttons)
- Modify: `src/quickdbd_cli/assets/style.css` (`.details`)
- Modify: `docs/reading-the-diagram.md`

**Interfaces:**
- Produces: `glideTo(view, ms)` in `viewer.js`.
  - It animates `S.view` with ease-out over `ms` (350).
  - It is instant under `prefers-reduced-motion` and while `applyingHash`.
  - The next pointerdown or wheel cancels it.

- [ ] **Step 1: Wire the glides.**
  - `fit(only, glide)` and `centerOn(id)` glide when called from user actions: `#zfit`, tree click, Enter in search, path fit, Show both tables.
  - The initial load and hash reads stay instant.
  - `#zin` / `#zout` glide over 200ms.
- [ ] **Step 2: Make the details panel slide.** It is always `display: block`; closed means `visibility: hidden; opacity: 0; transform: translateX(16px); pointer-events: none`, and open transitions back over 200ms.
- [ ] **Step 3: Add a paragraph to `docs/reading-the-diagram.md`** under the relationships section:
  - hover a line to light it;
  - click it to lock it and open the card;
  - the `1` / `*` labels;
  - Copy JOIN and Show both tables;
  - Esc clears.
- [ ] **Step 4: Browser check:** fit glides, tree click glides, a wheel during a glide stops it, the panel slides. Run `.venv/bin/mkdocs build --strict`. Expected: no warnings.
- [ ] **Step 5: Commit** `git commit -m "viewer: glide zoom and fit, slide the details panel"`.

### Task 6: MkDocs hook: mini diagram and tour page

**Files:**
- Create: `hooks/home.py`
- Modify: `mkdocs.yml` (`hooks:` list and `extra_javascript:`)
- Test: `tests/test_home_hook.py`

**Interfaces:**
- Produces:
  - **`config.extra["home_mini"]`:** `{"svg": str, "steps": {line_index: ["t", table] | ["r", table, col]}}`.
    - `line_index` is 0-based within the snippet.
    - The snippet is the text of `<pre ... id="t-text">` in `overrides/home.html`, tags stripped and `html.unescape`d.
    - Positions are fixed by name: `{"Customer": (0, 10), "Order": (300, 0)}`; any other table goes 300px right of the last.
  - **`{site_dir}/assets/tour/adventureworks.html`:** the `gallery/adventureworks` sources built with `--by-group` through `Project`, the way `scripts/build_gallery.py` builds a demo.
  - **Functions:** `hooks/home.py` `mini_diagram(home_html: str) -> dict`, `build_tour(site_dir: Path) -> Path`, and the MkDocs events `on_config` / `on_post_build`.

- [ ] **Step 1: Write the failing tests.**
  - `test_mini_diagram_steps`, on the real `overrides/home.html`: `steps == {1: ["t","Order"], 3: ["r","Order","OrderId"], 4: ["r","Order","CustomerId"], 5: ["r","Order","Status"], 7: ["t","Customer"], 9: ["r","Customer","CustomerId"], 10: ["r","Customer","Email"]}`.
  - `test_mini_diagram_svg`: the SVG has `data-id="Order"`, `data-id="Customer"` and one `class="e"`, and no `@font-face`.
  - `test_build_tour`, into `tmp_path`: the output exists and its `qdbd-data` model has 68 tables.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_home_hook.py -q`. Expected: FAIL (no module).
- [ ] **Step 3: Implement `hooks/home.py`.**
  - Steps come from the compiled schema's table and column `line` numbers minus the snippet's start line.
  - Fonts are stripped from the SVG; the page loads Inter itself.
  - Register the hook in `mkdocs.yml`.
- [ ] **Step 4: Run** the tests and `.venv/bin/mkdocs build --strict`. Expected: PASS, and `site/assets/tour/adventureworks.html` exists.
- [ ] **Step 5: Commit** `git commit -m "docs: hook builds the home mini diagram and the tour page"`.

### Task 7: Landing hero, headings, card light, shared motion helpers

**Files:**
- Modify: `overrides/home.html` (hero markup: a `.qh-hero__head` holding the author pill, eyebrow and h1; h1 accent on its own line)
- Modify: `docs/stylesheets/home.css`
- Create: `docs/javascripts/home.js`

**Interfaces:**
- Produces: `window.qhome = {reduce: bool, wait(ms), onView(el, fn, margin), typer(el) -> {play(onLine, speed), show(), clear()}}`.
  - `home.js` runs `init` through `document$.subscribe` when present, else on load.
  - `init` returns early without `.qh` and marks done nodes with `data-qh`, so instant navigation re-runs cleanly.

- [ ] **Step 1: Hero layout,** following `home-layout.html`:
  - Grid `minmax(0,1fr) minmax(0,1.3fr)`, gap `36px 40px`, with the head spanning both columns.
  - Callout at `left: -32px; bottom: -30px` above 960px.
  - The screenshot rises in once on load (`translateY(28px)`, 0.9s). No tilt.
- [ ] **Step 2: Motion helpers and global effects,** following `home-motion-2.html`:
  - h2 and h1 word split (custom `q-w` elements, splitting only on real spaces), with a 45ms stagger;
  - card border light following the cursor;
  - scroll reveal for step lists, gallery and FAQ;
  - every effect gated on `qhome.reduce`.
- [ ] **Step 3: Browser check** at 1280, 1512 and 390:
  - the hero frame's right edge equals `.qh-compare`'s right edge;
  - `scrollWidth == innerWidth` at 390;
  - no console errors after navigating away and back with instant navigation.
- [ ] **Step 4: Commit** `git commit -m "docs: hero redesign and shared home motion"`.

### Task 8: Live demo section

**Files:**
- Modify: `overrides/home.html` (section after the hero, markup from `home-tour-section.html`; the iframe `src` is `assets/tour/adventureworks.html`, inserted by JS only when allowed)
- Modify: `docs/stylesheets/home.css`
- Create: `docs/javascripts/home-tour.js`

**Interfaces:**
- Consumes:
  - `qhome` (Task 7);
  - the tour page (Task 6);
  - the viewer contract (Task 3): `#q`, `.ti[data-id]`, `.hit path[data-k]`, `#rcopy`, `#filter`, `#pathto`, `#pathsql`, `#zfit`, and Escape to clear.

- [ ] **Step 1: Port the tour** from `home-tour.html`:
  - the four chapters, `DUR = [7, 8, 7, 11]` seconds;
  - hover takes control, with a 1.5s resume after leaving;
  - chapter-card jumps;
  - start at 40% visible.
  - Reset uses Escape plus clearing `#q` and `#filter`. No page patches are needed now (Task 2 Step 4).
- [ ] **Step 2: Fallbacks.**
  - Below 760px or under `(hover: none)`: no iframe. Show `hero.png` with an "Open the live demo" link to `demo/adventureworks/`, and hide the chapter cards.
  - Under reduced motion: an interactive iframe in the "Your turn" state; chapter clicks apply the end state instantly.
  - If the iframe errors or lacks `qdbd-data`: show the still image.
- [ ] **Step 3: Browser check:**
  - the four chapters run with no console errors on `mkdocs serve`;
  - 390px shows the still image;
  - reduced motion (Playwright `reduced_motion="reduce"`) means no autoplay.
- [ ] **Step 4: Commit** `git commit -m "docs: live demo tour on the home page"`.

### Task 9: Compare cards and flow diagram motion

**Files:**
- Modify: `docs/stylesheets/home.css`, `docs/javascripts/home.js`

- [ ] **Step 1: Port from `home-motion-1.html`:**
  - Compare: staggered rise, rows and marks pop, `settled` 1.7s later (side cards 0.62 opacity, scale 0.98; qdbd card lifts, with the conic border light on a 5s loop).
  - Flow: SVG wires above 960px, laid out from box `offset*` values (not `getBoundingClientRect`, which includes reveal transforms); build-in order; a pulse every 3.8s, inputs round-robin; hover lights the path.
  - Set the delays after the hide classes plus a reflow, so the hiding itself isn't delayed (the mockup bug).
- [ ] **Step 2: Browser check:** build-in order screenshots, hover lighting, arrows back at 960px and below.
- [ ] **Step 3: Commit** `git commit -m "docs: compare cards and flow diagram motion"`.

### Task 10: Text to diagram and quick start

**Files:**
- Modify: `overrides/home.html` (replace the `path.png` figure with `<div class="qh-mini">` filled from `config.extra.home_mini.svg`; pass `home_mini.steps` as JSON in a `<script type="application/json" id="qh-mini-steps">`)
- Modify: `docs/stylesheets/home.css`
- Create: `docs/javascripts/home-mini.js`

**Interfaces:**
- Consumes: `qhome.typer`, `qhome.onView` (Task 7), `home_mini` (Task 6), `Q`-free logic only (the docs page has no `render.js`).

- [ ] **Step 1: Port from `home-motion-2.html`:**
  - tab underline, panel fade, typing;
  - the mini diagram builds from `qh-mini-steps`, not a hard-coded map: the line draws once both tables exist and lights after typing ends; card and Replay included;
  - the card is clamped inside the frame, with `pre-wrap` on narrow screens;
  - quick-start track, badge rings, typed commands.
- [ ] **Step 2: Browser check:** the diagram builds in step with typing at 1512; no sideways scroll at 390; switching tabs mid-typing cancels cleanly.
- [ ] **Step 3: Commit** `git commit -m "docs: typing code builds a live mini diagram; quick-start track"`.

### Task 11: PR section, gallery, FAQ, buttons, closing

**Files:**
- Modify: `overrides/home.html` (PR section markup: list in a row, then a figure with `.qh-pr__stage` holding the image link and the comment)
- Modify: `docs/stylesheets/home.css`, `docs/javascripts/home.js`

- [ ] **Step 1: Port from `home-layout.html` and `home-motion-2.html`:**
  - PR: the comment at `left: 24px` inside the image (not the mockup's `-28px`), slides up, rows flash; the stage tilts in on scroll.
  - Gallery image zoom on hover; smooth FAQ with a rotating plus.
  - Primary button shimmer; typed closing command and drifting glow; `.qh-split` gap 28px.
- [ ] **Step 2: Browser check** at 1280, 1512 and 390 with reduced motion on and off.
- [ ] **Step 3: Commit** `git commit -m "docs: PR section layout and remaining home motion"`.

### Task 12: Verify, version, ship

**Files:**
- Modify: `pyproject.toml`, `src/quickdbd_cli/__init__.py`, plus version snippets in `README.md` and the docs (as for earlier releases)

- [ ] **Step 1: Run everything:** `.venv/bin/ruff check src tests scripts hooks && .venv/bin/ruff format --check src tests scripts hooks && .venv/bin/pytest -q && .venv/bin/mkdocs build --strict`. Expected: all pass.
- [ ] **Step 2: Final Playwright pass** over the viewer and the landing page (every check above), with screenshots reviewed.
- [ ] **Step 3: Bump the patch version** (0.3.3 → 0.3.4) everywhere earlier bumps touched. Commit.
- [ ] **Step 4: Ship:** push, open the PR into `main`, wait for CI, merge, then `scripts/release.sh` (Node 22 on `PATH`; stash local layout files around it), and verify on PyPI.
