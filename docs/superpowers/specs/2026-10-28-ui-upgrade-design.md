# UI upgrade: lit relationships in the viewer, motion on qdbd.dev

Date: 2026-10-28. Status: design approved in mockups, awaiting sign-off on this document.

## Why

The owner likes the current tone of qdbd.dev and the viewer, but both feel static. Two prompts:

- In dbdiagram.io, relationship lines light up when you pick a table, with moving dashes and `1` / `0..*` labels. qdbd only recolours them.
- The landing page has no motion: sections, cards and diagrams just sit there. "Still static, more motions, more animation."

Plus one real defect: dragging a table is slow on big diagrams.

Success means the viewer feels alive and stays fast at 200+ tables, and the landing page has visible, purposeful motion in every section without losing its current look.

## Scope and order

Two parts, built in this order, because the landing page's live tour drives the new viewer features:

1. **Viewer** (`render.js`, `viewer.js`, `style.css`): every page qdbd builds, `qdbd serve` (editable and `--read-only`), shared gists, and the VS Code preview.
2. **Landing page** (`overrides/home.html`, `docs/stylesheets/home.css`, plus a script): qdbd.dev only. The other docs pages get no motion. `reading-the-diagram.md` gains a short note on the new line behaviour (see "Images and docs pages").

## Reference mockups

`docs/superpowers/specs/assets/2026-10-28-ui-upgrade/` holds the throwaway prototypes the owner approved. They show the exact look, timings and easings. They patch the DOM from outside, so treat them as references, not code to paste:

| File | Shows |
| --- | --- |
| `viewer-lit-relationships.html` | lit lines, labels, flowing dashes, line hover/click, the relationship card |
| `home-tour-section.html`, `home-tour.html` | the live demo section and its scripted cursor |
| `home-motion-1.html` | compare cards, the flow diagram wires and pulses, scroll reveal |
| `home-motion-2.html` | word-by-word headings, typing code, the live mini diagram, quick-start track, card border light, FAQ, buttons |
| `home-layout.html` | the hero layout and the PR section layout |
| `snippet.txt` | the "From text to diagram" schema |

## Part 1: Viewer

### Lit relationships (decided by the owner)

- **Keep the curved lines.** A lit line gets three things:
  - a blue stroke (`#4361ee` light / `#8aa0ff` dark), about 2.2px;
  - flowing dashes on top (`stroke-dasharray: 4 18`, 1.1s loop, a deeper blue);
  - cardinality labels at both ends.
- **Labels:** `1`, `0..1`, `*` and `0..*` for `one`, `zeroOne`, `many` and `zeroMany`. They sit just off each end, on the side the line leaves from, with a background-coloured halo so they stay readable. **Labels appear only on lit lines.**
- **The joined columns' rows** are highlighted in both tables.
- **What lights a line:**
  - *Table hover* previews: that table's lines light up.
  - *Table click* locks: today's focus behaviour, now with lit lines.
  - *Line hover* previews that one line.
  - *Line click* locks that line and opens the relationship card. Every other table dims to about 0.18 and every other line to about 0.07.
- **Exclusivity:** a table click replaces a locked line, and a line click replaces a table focus. Esc and a click on empty canvas clear both.
- **Hit area:** lines need a transparent hit target about 14px wide so they can be hovered and clicked.
- **Join path:** the existing amber path highlight also gets flowing dashes, in amber.

### Relationship card (approved: "that's what I'm looking for")

A small popover next to the click point. It contains, in order:

1. `Order.CustomerId  * — 1  Customer.CustomerId` (the cardinality in blue).
2. A plain-English sentence: "Each Customer row has many Order rows."
3. The JOIN, from render.js's existing SQL builder (`pathSql` with one step, `stepPairs` for composite refs), so quoting and composite keys match `qdbd path`.
4. **Copy JOIN** and **Show both tables**. Show both tables filters the view to the two tables.

It opens with a short scale-and-fade (about 160ms) and closes on Esc, on a click elsewhere, or when the selection changes.

**Blocked clipboard (my call).** Where the clipboard is blocked, for example the VS Code preview (its iframe has no `clipboard-write`):

- Copy JOIN, and the existing Copy SQL, select the SQL text and show "Press Ctrl/Cmd+C" instead of failing silently.
- No extension change and no new embed message.

### Drag performance (owner: "the slowness of table drags")

- **Cause:** every pointermove frame re-renders all edges and re-walks every table and edge for focus classes.
- **Fix:** while dragging, redraw only the edges that touch the dragged table, and don't redo focus classes per frame.
- **Goal:** smooth dragging on `examples/synthetic` (200 tables). The builder picks the method and how to measure it.

### Polish (my calls, owner agreed)

- **Zoom, fit and jump-to-table** glide (about 300–400ms ease-out) instead of snapping. A new gesture interrupts a glide.
- **The details panel** slides in.
- **Tables** lift slightly on hover (a soft drop shadow).

### Viewer rules

- **Exports don't change.** PNG, SVG and draw.io never contain lit state, labels, dashes or the card, and default renders stay byte-identical.
- **Reduced motion:** with `prefers-reduced-motion`, lines still light up and labels still show, but the dashes stop moving and glides are instant.
- **No network:** built pages stay self-contained and load nothing from the network.
- **Code placement:**
  - Pure logic (label positions and text, card text, join SQL) goes in `render.js`, so Python can test it through `jsrt` and the page and CLI can't drift.
  - DOM wiring goes in `viewer.js`.
- **Synthetic pointer events:** `viewer.js` must tolerate them (`setPointerCapture` can throw for synthetic events; catch it), because the landing-page tour drives the viewer that way.
- **Unchanged:**
  - URL-hash state (`f t p m r z c`) keeps working. Putting a locked line in the hash is the builder's call.
  - The VS Code embed messages stay the same.
  - `MIN_VERSION` doesn't change, since no CLI flags change.

## Part 2: Landing page

**Approved by the owner:** the layout of each section, and that every section moves. The details below are taken from the mockups.

### Hero (redesigned to respect the page margins)

- **Layout:**
  - The author pill, the version line and the headline span the full content width. "readable at 200+ tables" goes on its own line, in the accent colour.
  - Below that, two columns (about 1 : 1.3) inside the normal margins. Left: intro, buttons, install command, the dbt and VS Code notes. Right: the existing AdventureWorks screenshot (`hero.png`).
  - The screenshot's right edge lines up exactly with every other section's right edge. The owner rejected both a screenshot bleeding past the margin and a live diagram in place of the screenshot.
- **The SalesOrderHeader callout** overlaps the screenshot's bottom-left corner.
- **Motion:**
  - The headline words rise in one by one out of a blur, and the text below follows in sequence.
  - The screenshot rises in once on load.
  - No tilt: it pushed the right edge off the margin.

### Live demo (new section, directly under the hero)

- **Header:** eyebrow "Live demo", heading "The real page, driven by a script", and a line saying it's the actual viewer running AdventureWorks (68 tables) and that moving the mouse over it takes control.
- **The frame:**
  - A big framed window holds the real AdventureWorks demo page in an iframe, scaled to fit.
  - A fake cursor drives it with real events: typing, clicks, Enter.
  - The bar shows "Playing" with a pulsing dot.
- **The four chapters,** played in a loop:
  1. **Search:** type "SalesOrderH", click SalesOrderHeader; its lines light up.
  2. **Relationships:** click the SalesOrderHeader to Customer line, then click Copy JOIN in the card.
  3. **Selectors:** type `+SalesOrderDetail` into the filter and press Enter; the diagram shrinks to 23 tables.
  4. **Join paths:** pick SalesOrderDetail, path to Person, then hover Copy SQL. The path flows in amber.
- **Chapter cards** under the frame have a progress bar each, and clicking one jumps to that chapter.
- **Hover means control:** the tour stops, the label becomes "Your turn", the cursor hides and the page is fully usable. Leaving resumes the tour after about 1.5s.
- **Starting:** the tour starts when the frame is about 40% visible.
- **The page in the iframe** must be same-origin, because the script reaches into it.
- **Phones and touch screens (my call):** below 760px wide, or on devices without hover (`(hover: none)`):
  - No iframe is loaded (a 1440px page scaled to fit a phone is unreadable, and heavy).
  - The frame shows a still screenshot of the viewer with an "Open the live demo" link to the AdventureWorks demo.
  - The chapter cards are hidden.
- **Reduced motion (my call):**
  - No autoplay and no cursor. The iframe loads as a normal interactive page in the "Your turn" state.
  - Clicking a chapter card applies that chapter's end state instantly.

### Compare cards ("Hand-drawn diagrams go stale...")

- The cards rise in staggered, and each row slides in with its check or cross popping.
- About 1.7s later the two side cards fade back (about 0.62 opacity, slightly smaller) and the qdbd card lifts, with a stronger glow and a mint light running around its border on a slow loop.
- Hovering a side card brings it back to full strength.

### Flow diagram ("One text file in, every format out")

- **Wires instead of arrows:** above 960px, the text arrows become curved SVG wires in the viewer's relationship-line style, from each input to qdbd and from qdbd to each output.
- **Build-in order:** inputs slide in, input wires draw, qdbd appears, output wires draw, outputs slide in.
- **Pulse every ~3.8s:**
  1. A glowing pulse runs from one input to qdbd, taking the inputs in turn.
  2. qdbd flashes and "check · layout · render" lights up word by word.
  3. Pulses fan out to all four outputs, which flash.
- **Hover:** hovering a box lights its path with flowing dashes, like hovering a table.
- **Narrow screens** keep the arrows.

### From text to diagram

- **Tabs:** the underline slides between tabs, and each panel fades in.
- **Typing:** the code types itself with a cursor when the section scrolls into view and when a tab is picked, keeping its syntax colours.
- **Live mini diagram:**
  - The path-finder screenshot is replaced by a small diagram of the exact schema on the left (Order, Customer), in a light viewer-style frame.
  - It builds as the text types: a table appears when its name line is typed, and each row appears with its line.
  - Once both ends exist, the relationship line draws itself, then lights up with dashes, the `*` / `1` labels and the relationship card.
  - A Replay button reruns it.
- **The mini diagram must come from qdbd itself,** rendered from the snippet at docs build time, so it can never drift from the text.

### Quick start ("Your first diagram in two minutes")

- A glowing track fills from step 1 to step 4.
- Each number pops with a ring as the track reaches it, then that step's command types itself.

### PR review ("See what a branch changes before you merge it")

- **Layout:** the three points sit in a row, with a full-width diff screenshot below. The github-actions comment floats over the screenshot's bottom-left corner. This replaces the old side-by-side layout, which left dead space; the owner said they hate space next to images.
- **Comment position (my call):** the comment sits about 24px inside the screenshot's left edge. The mockup's `left: -28px` overhang crosses the page margin, so it's wrong.
- **Motion:**
  - The comment slides up when it scrolls in.
  - The table rows arrive one by one, each with a short green flash.
  - The screenshot tilts up into place as it scrolls in.

### Everywhere else

- **Headings:** every section heading rises in word by word.
- **Card borders:** a soft light follows the cursor along the borders of cards (compare, flow boxes, gallery, steps, tabs, comment, chapter cards).
- **Gallery:** images zoom slightly on hover.
- **FAQ:** answers slide open, and the + turns into an ×.
- **Primary buttons:** a shimmer passes over them every few seconds.
- **Closing section:** the install command types itself over a slowly drifting glow.
- **Spacing:** the gap between the code panel and the mini diagram is a bit tighter.

### Landing-page rules

- **Margins:** nothing crosses the page margins. There is no sideways scroll at 390px wide.
- **Reduced motion:** everything shows in its final state with no movement. The live demo follows its own reduced-motion rule above.
- **Fallbacks:** newer CSS (scroll-driven animations, `::details-content`) must degrade to "no animation", never to broken layout.
- **Instant navigation:** the site uses MkDocs Material's `navigation.instant`, so the home-page script must work after an instant navigation back to the home page, not only on a full load.
- **No build step:** no new runtime dependencies or npm build. Plain JS and CSS, like today.

## Images and docs pages (my call)

- **No images are regenerated in this change:** not `hero.png`, `path.png`, `details.png`, nor the gallery thumbnails.
  - The owner wants the current hero screenshot kept.
  - Lit lines only appear after an interaction or a `t=` link, so the stills stay accurate enough.
  - Regenerating would also capture dashes frozen mid-animation, so screenshots would differ from run to run.
- **`reading-the-diagram.md`** gets a short paragraph: hover or click a line to light it, the labels, and the relationship card with Copy JOIN. No other docs text changes.

## Non-goals

- Changing exports, the parser, the layout engine or any CLI behaviour.
- Animating docs pages other than the landing page.
- A new design language: colours, fonts and tone stay as they are.

## Anti-goals (would count as failure even if it works)

- Motion that makes text harder to read, or that janks on a 200-table diagram.
- Losing the AdventureWorks hero screenshot.
- Anything that breaks the right margin, or leaves dead space beside an image.
- A built qdbd page that loads something from the network.

## Testing

- **Python tests** for the new pure `render.js` helpers through `jsrt`:
  - label text and positions;
  - card sentence;
  - single-relationship JOIN, including composite and table-level refs.
- **Existing guards keep passing:** the determinism test (byte-identical builds) and the export tests.
- **Tour guard (my call):** a test that the elements the landing-page tour depends on still exist in a built page (search box, filter box, path box, fit button, tree items, line hit targets, the card's Copy JOIN). Then a viewer refactor can't silently break the tour.
- **Manual browser check with Playwright** (not a declared dependency; the system Chrome works):
  - **Viewer:** hover and click tables and lines, the card, Copy JOIN, Esc, drag smoothness on `examples/synthetic`, dark theme, the VS Code preview (including the copy fallback).
  - **Landing page:**
    - all four tour chapters run without console errors;
    - the still-image fallback appears at 390px and on touch;
    - with reduced motion there's no autoplay;
    - no sideways scroll at 390px;
    - right edges line up at 1280px and 1512px.
- **`mkdocs build --strict`** passes.

## Left to the builder

- How the drag fix is done and measured.
- How the glides are implemented.
- Whether a locked line goes in the URL hash.
- Which page the tour's iframe loads. It must be same-origin and must work with `mkdocs serve` and on Pages.
- How the mini diagram's "line typed → table or row appears" mapping is derived. It must follow the snippet, not be hand-kept.
- How the landing-page script is split and where it lives.
- Exact pixel values not fixed above: use the mockups as the guide.

## Release

- **PyPI:** the viewer changes ship in the next qdbd release. Bump `pyproject.toml` and `__init__.py`.
- **VS Code extension:** no change needed.
- **Docs:** the landing page deploys with the docs, through the existing Pages workflow.
