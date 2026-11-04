# qdbd demo video (60 s) for the README and qdbd.dev

## Context

qdbd has docs, live demos and a scripted live tour, but no video. Goal: a professional 60-second demo that shows **local features first** (write the schema as .txt/.dbml, `qdbd build`, open the HTML, explore it, live-edit with `qdbd serve`), then the VS Code extension, then a quick "and more" (exports, PR review). **Sharing is never shown or mentioned.**

Outcome:
- `docs/assets/video/qdbd-demo.mp4`: 1920x1080, about 60 s, music plus on-screen text.
- Plays on the qdbd.dev home page; a poster image in the README links to it.
- A re-renderable project in `videos/qdbd-demo/`, so the video can be rebuilt when the UI changes.

## Brief: what you chose

| Field | Answer |
|---|---|
| Destination | README + docs site: 16:9, 1920x1080, muted autoplay |
| Audio | Music + on-screen text, no voiceover. Music from the HeyGen free library |
| Length | ~60 s |
| Footage | Real footage of the real tool, plus motion polish (title cards, zooms, callouts) |
| Local part | Build from .txt/.dbml, open the HTML, explore (search, click, focus), live editor (`qdbd serve`) |
| And more | Exports, PR review (GitHub Action) |
| Schemas | Tiny shop (.txt + .dbml twin) to build; AdventureWorks DW to explore; 2 s shot of the 200-table one |
| Look | Match qdbd.dev |
| Process | Storyboard sketches first. I build, you review (sketch sheet + final preview) |
| Where | In the repo + embedded. Branch from `main`, PR, merge |

## My calls (inferred; veto any at approval)

1. **Message:** "Database diagrams that live in git, readable at 200+ tables" (the qdbd.dev headline).
   - CTA: `pipx install quickdbd-cli` (as on the site) · qdbd.dev · VS Code Marketplace · Open VSX.
2. **Terminal shots:** real commands, run for real; their output is captured verbatim, then typeset in a terminal window inside the video. Crisper than a screen grab; the words are 100% real.
3. **Never on screen:** `qdbd share`, the Share menu, the viewer's Link button, read-only tunnels. No emoji or icon glyphs in on-screen text (the UI's own icons in footage are fine).
4. **PR review shot:** no PR in this repo has a qdbd comment with real changes (all say "No schema changes").
   - So it shows the real gallery `diff` demo (green NEW and amber CHANGED headers, plus the banner) next to the real `qdbd diff --format markdown` output on a card labelled "PR comment".
   - If you want the literal GitHub page instead: a throwaway PR in a scratch repo. That's public, so only on your say-so.
5. **Exports shot:** the real PNG, SVG and draw.io exports of the shop schema. The draw.io file is shown open in app.diagrams.net if that loads cleanly; otherwise the toolbar buttons and three file cards.
6. **Legibility at README width (~760 px):** on-screen text ≥ 56 px at 1080p. Footage is recorded at 2x and cropped or zoomed so UI text stays readable.
7. **Docs embed:** new section on `overrides/home.html` between the hero and the live tour, with `id="demo"` and the title "qdbd in 60 seconds".
   - `<video muted loop playsinline poster>`, playing only while visible.
   - With reduced motion: poster plus controls, no autoplay. This reuses the `window.qhome.reduce` + IntersectionObserver pattern from `docs/javascripts/home-tour.js`.
8. **README:** a poster image under the hero caption, linking to `https://qdbd.dev/#demo`. The poster carries the words "Watch the 60-second demo", not a play icon.
   - Optional, yours (about 1 min): drag the MP4 into GitHub's README editor to get an inline player.
9. **No PyPI release:** there's no package change. The README poster reaches PyPI with the next normal release.
10. **HyperFrames route:** `general-video` (a footage-led edit), `flow: automation`, `storyboard: yes`. Approving this plan counts as the storyboard's plan pass.
11. **Music file:** not committed (its license isn't for redistribution), only baked into the MP4. Check the track's licence allows a public promo before using it. **If it doesn't, or it's unclear: go silent** (your call). Drop the music and say so; the site plays the video muted anyway.

## Storyboard (60 s, 30 fps)

| # | Time | Scene | Visual (real footage unless noted) | On-screen text |
|---|---|---|---|---|
| 1 | 0:00-0:05 | Hook | 200-table `examples/synthetic` diagram, slow zoom, dimmed; qdbd wordmark | "Database diagrams that live in git" / "readable at 200+ tables" |
| 2 | 0:05-0:12 | Write | Two editor panes: `shop.txt` (QuickDBD) and `shop.dbml` (made by `qdbd convert`), typing in | "Write your schema as text. QuickDBD or DBML." |
| 3 | 0:12-0:18 | Build | Terminal (my call 2): `qdbd build shop.dbml -o shop.html` with real output, then `open shop.html` | "One command. One self-contained HTML file." |
| 4 | 0:18-0:22 | Open | Browser window grows from the terminal; the shop diagram appears | "Opens in any browser. Works offline." |
| 5 | 0:22-0:34 | Explore | AdventureWorks DW (28 tables, regions): `/` search FactInternetSales, Enter, click opens details, neighbours stay lit and the rest dims, hover lights lines; minimap | "Search" / "Click for columns and keys" / "Focus on what's connected" |
| 6 | 0:34-0:43 | Live edit | `qdbd serve shop.txt`: type a `Review` table with an FK to Product; autosave; it appears next to Product; drag it | "qdbd serve: edit, save, the diagram follows" |
| 7 | 0:43-0:52 | VS Code | Real VS Code: shop.txt with the diagram beside it; a typo gets a red squiggle (real qdbd error); the cursor moves into a table and the diagram follows | "VS Code and Cursor: errors as you type, diagram beside your code" |
| 8 | 0:52-0:56 | And more | Exports (2 s, my call 5), then PR review (2 s, my call 4) | "Export PNG, SVG, draw.io" / "See schema changes in every pull request" |
| 9 | 0:56-1:00 | Outro | Wordmark, `pipx install quickdbd-cli`, qdbd.dev, Marketplace · Open VSX; holds so the loop restarts cleanly | — |

## Build steps

Node 22 for everything HyperFrames: `export PATH="$HOME/.nvm/versions/node/v22.23.2/bin:$PATH"`.

1. **Branch and spec.**
   - `git switch -c docs/demo-video main`.
   - Write this brief and storyboard to `docs/superpowers/specs/2026-10-30-demo-video-design.md`.
2. **HyperFrames project.**
   - `npx hyperframes skills update general-video`.
   - `npx hyperframes init videos/qdbd-demo --non-interactive --example=blank --skill=general-video`.
   - Write `BRIEF.md` (canonical frontmatter) and record the preferences.
   - Run `npx hyperframes auth status` and relay its output.
   - `.gitignore`: `node_modules/`, `renders/`, `snapshots/`, recorded clips and frames, the music file.
3. **Music access.** Install the HeyGen CLI from its verified release instructions. **You** run `heygen auth login --oauth` (one browser click).
4. **Capture workspace and scripts** in `videos/qdbd-demo/capture/` (dev-only; `videos/` isn't in the sdist include list).
   - `shop.txt`: 4 tables (Customer, Order, OrderLine, Product), trimmed from `examples/quickdbd-sample.txt`.
   - `shop.dbml`: made from it with `qdbd convert`.
   - `record.py` (Playwright, `.venv`, system Chrome via `channel="chrome"`, deviceScaleFactor 2):
     - Recording: CDP `Page.startScreencast`, then ffmpeg to MP4, using the frame timestamps.
     - Cursor and click ripples are injected into the page, in the same look as `.qh-cursor` from the home tour.
     - Viewer selectors come from `tests/test_viewer_contract.py`, the same pinned elements the home tour drives.
     - Clips: synthetic slow zoom; shop diagram opening; AdventureWorks explore; `qdbd serve` live edit.
     - Built with plain `qdbd build`, so there's no gallery "All demos" link: `gallery/adventureworks-dw --by-group` (regions need `--by-group`, as in its `build_args` in `gallery/demos.toml`) and `examples/synthetic`.
     - Injected CSS hides the viewer's Link button (`#xlink`) in every shot (embed mode already hides it).
     - Diff shot: `qdbd build` can't take a file as `--diff-base`, so it uses the `scripts/build_gallery.py` output for the `diff` demo, with the "All demos" link hidden by CSS.
     - The markdown card comes from `qdbd diff OLD NEW --format markdown`.
   - Terminal text: run the real commands; save stdout verbatim to `capture/terminal/*.txt`.
   - VS Code: a small launcher `capture/vscode.mjs`. `run.mjs` runs the whole test suite in its own workspace and stops on `Ledger`, so it never opens `shop.txt`.
     - The launcher copies `run.mjs`'s setup: `extensionDevelopmentPath`, `--remote-debugging-port`, and VS Code 1.143.1 (already in `vscode/.vscode-test`).
     - It opens the shop workspace with this checkout's extension and the `.venv` qdbd. The "Extension Development Host" title bar is cropped out.
     - Dark Modern theme, zoomed UI. Playwright `connect_over_cdp` takes a screencast of the workbench.
     - Fallback: fresh 2x stills with motion.
   - **Never** run `qdbd serve` on `examples/synthetic`: it rewrites the committed layout file. Serve only the scratch shop copy.
5. **Sketch sheet (gate: you).** `storyboard.html` wireframes for all 9 scenes; revise until you confirm.
6. **Build scenes.** One composition per scene.
   - Look from the repo's own tokens: `docs/stylesheets/extra.css` + `home.css` (Geist headings, Inter, mono, `--bp-*` colours), plus `docs/assets/img/logo-wordmark-*.svg`.
   - Footage gets punch-in zooms and callouts.
7. **Music.** `/media-use` resolve BGM: "upbeat minimal tech, no vocals". Fade in 0.5 s, out 2 s; cut on beats where it's clean.
8. **Checks.**
   - `npx hyperframes lint`, `npx hyperframes check`.
   - `npx hyperframes snapshot`: inspect the contact sheet at 760 px wide, and check that no sharing UI appears in any frame.
9. **Final preview (gate: you), then render.**
   - `npx hyperframes render --quality high`.
   - ffmpeg H.264, `+faststart`, ≤ 8 MB, to `docs/assets/video/qdbd-demo.mp4`.
   - Poster to `docs/assets/img/demo-poster.jpg`.
10. **Embed.** Video section in `overrides/home.html` + `docs/stylesheets/home.css` (reuse `.qh-frame` / `.qh-fig`); play-when-visible JS beside `home-tour.js`; poster block in `README.md`.
11. **Ship.** Run the verification below, then PR, CI, merge (docs deploy from `main` via `erd.yml`). No version bump.

## Files

- **New:**
  - `videos/qdbd-demo/**` (project, capture scripts)
  - `docs/assets/video/qdbd-demo.mp4`
  - `docs/assets/img/demo-poster.jpg`
  - `docs/superpowers/specs/2026-10-30-demo-video-design.md`
- **Edit:** `overrides/home.html`, `docs/stylesheets/home.css`, `docs/javascripts/` (small play-when-visible addition), `README.md`.
- **Reuse:**
  - `docs/javascripts/home-tour.js` (cursor look, visibility, reduced motion)
  - `tests/test_viewer_contract.py` (stable viewer selectors)
  - `gallery/adventureworks-dw`, `gallery/diff`, `examples/synthetic`, `examples/quickdbd-sample.txt`
  - `vscode/test/integration/run.mjs`
  - the logo SVGs

## Verification

- **Video:** `ffprobe` shows 1920x1080, 58-62 s, H.264, ≤ 8 MB, with audio fades. The contact sheet is readable at 760 px; there's no sharing UI in any frame.
- **Docs:**
  - `.venv/bin/mkdocs build --strict` passes.
  - Playwright on the built site: the video autoplays muted when scrolled into view and pauses off-screen.
  - With reduced motion: poster plus controls.
  - At phone width: no horizontal scroll; the live tour still works.
- **Repo:**
  - `.venv/bin/ruff check src tests scripts`, `.venv/bin/ruff format --check src tests scripts` and `.venv/bin/pytest` still pass.
  - `git status` shows `examples/synthetic/qdbd.layout.json` unchanged.
- **README, after the merge:** the poster shows and links to `qdbd.dev/#demo`. Its image URL is an absolute `raw.githubusercontent.com/.../main/` link (so it works on PyPI), so it looks broken in the PR until the merge.

## Your actions (only 3)

1. One HeyGen sign-in click (step 3).
2. Confirm the sketch sheet (step 5).
3. Approve the final preview before render (step 9).

Time: capture scripts and recordings ~2 h; sketches ~20 min; build, music and render ~2 h; embed and PR ~45 min.
