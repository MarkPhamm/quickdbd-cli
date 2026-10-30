# qdbd.dev "blueprint" look

## Why

anfra.ai reads as futuristic and qdbd.dev did not. PR #68 had already taken anfra's section order and motion ideas; what was
missing was the visual skin: a drafting frame (full-width hairline rules, crosshair marks, fading rails, masked two-level
grid plates), a light paper-and-ink palette with one accent, Geist / Geist Mono with mono as the interface voice, flat
surfaces instead of glows, and short `cubic-bezier(.22, 1, .36, 1)` easing. The site also used four unrelated looks (navy
home page, navy docs with serif headings, light Inter gallery, white viewer). ER diagrams are engineering drawings, so the
system is drafting paper, not a copy of anfra's warm cream and violet.

Scope: home page, docs pages, demo gallery and its thumbnails. The diagram viewer (`style.css`, `render.js`) is unchanged.

## Tokens (`docs/stylesheets/extra.css` `:root`)

| Token | Value | Use |
|---|---|---|
| `--bp-paper` / `--bp-sheet` | `#f2f2ee` / `#fafaf7` | page / cards, code, frames |
| `--bp-ink` / `--bp-ink-2` / `--bp-ink-3` | `#15181e` / `#4a505b` / `#646a75` | text; ink-3 is at least 4.68:1 on paper, sheet and wash |
| `--bp-rule` / `--bp-rule-strong` | ink at .12 / .24 | every border and section rule |
| `--bp-grid-major` / `--bp-grid-minor` | ink at .07 / .04 | 120px / 24px grid |
| `--bp-accent` / `--bp-accent-press` / `--bp-wash` | `#2f5bea` / `#2448c4` / `#e8eefd` | links, CTAs, active states |
| `--bp-ease-out` / `-io` / `-pop` | `(.22,1,.36,1)` / `(.65,0,.35,1)` / `(.3,1.36,.6,1)` | all motion |

The older `--qd-*` names are aliases of these, so docs and home styles written against them follow the palette. The gallery
(`gallery/index.html`) and the thumbnail card (`scripts/gen_thumbnails.py` `CARD`) repeat the values inline because they
are standalone pages.

## Decisions

- **Light scheme only** for the docs (`palette.scheme: default`). The gallery keeps its light/dark toggle; its dark
  tokens are an ink-black version of the same system.
- **Fonts:** `theme.font: false`, Geist and Geist Mono loaded by `@import` in `extra.css`, because Material's font
  loader asks for 300/400/700 only and the headings use 600. The home page keeps the Inter `<link>`: the mini diagram is
  measured in Inter. Demos keep their embedded Inter.
- **Frames** (`home.css` `.qh-fig`): each figure sits in its own frame, as anfra does. Full-width rules run along the
  frame's top and bottom, and rails run down its two edges, past the rules, fading out. A 25px crosshair marks each
  corner and a drafting grid fills the box. Split sections alternate the frame's side (diagram right, screenshot left,
  chat right), so the lines move from section to section; text-only sections have no lines. An earlier version put
  the same two rails at the page edges on every section, which read as one static grid. `.qh-plate` (a masked grid,
  no frame) is left for the hero.
- **The one bold element** is the hero screenshot as a drawing sheet: zone ticks (1–6, A–D), a dimension line along
  the selected table (FactInternetSales in AdventureWorks DW) with a "26 cols" label, and a title block. The page load drafts it in one sequence (zones, frame,
  dimension line, notes) instead of separate blur-in reveals.
  - The dimension line is in `hero.png`'s pixel space (`viewBox 0 0 1440 860`); regenerating `hero.png` means
    re-measuring it.
  - A leader line from the floating callout to the table was planned. It was dropped because the callout is sized in
    px while the image scales, so the line could not stay attached.
- **Motion:** reveals are 0.3–0.42s with an 8px lift and no blur. Hover is 160ms linear; press is a 90ms scale to .97.
  The scripted tour and the typing mini diagram keep their timing.
- **Dropped:**
  - the button shine
  - the drifting glow behind the closing CTA, replaced by a grid patch
  - the blue and mint glows
  - the planned slow pan of the hero grid
- **Tour:** `home-tour.js` sets `data-theme="light"` inside the tour iframe on load. The viewer's `applyTheme()`
  follows the OS on non-embed pages and ignores `?theme=`, so dark-OS visitors got a dark viewer on a light page.

## Left out

The viewer theme, the VS Code extension, a docs dark mode, and an accent marker on the right-hand TOC rail.
