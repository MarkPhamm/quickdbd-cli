# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`quickdbd-cli` (command `qdbd`, on PyPI) compiles QuickDBD-syntax `.txt` schemas, or a dbt `manifest.json`, into an interactive single-file HTML ER diagram that stays usable at 200+ tables. It also exports PNG, SVG and draw.io, diffs schemas against a git ref, and ships a composite GitHub Action (`action.yml`). The docs site (MkDocs Material) and live demos are published to GitHub Pages: docs at `/`, demos at `/demo/` and `/demo/jaffle/`.

## Commands

```bash
uv venv && uv pip install -e ".[dev,docs]"            # Python 3.11+; .venv is the project env
.venv/bin/pytest                                       # full suite (~20s; layout tests run ELK)
.venv/bin/pytest tests/test_parser.py -k duplicate     # one file / one test
.venv/bin/ruff check src tests scripts && .venv/bin/ruff format src tests scripts   # CI runs both (format --check)
.venv/bin/mkdocs build --strict                        # docs; CI fails on broken links
.venv/bin/qdbd build examples/synthetic -o /tmp/d.html # 200-table smoke test
python scripts/gen_schema.py                           # regenerate examples/synthetic (deterministic)
python scripts/gen_font_metrics.py                     # regenerate assets/font-metrics.json (needs fonttools)
PATH="$PWD/.venv/bin:$PATH" scripts/release.sh         # release (see below)
```

UI changes need a real browser check. Playwright isn't a declared dependency (`uv pip install -p .venv playwright`); it can drive the system Chrome with `p.chromium.launch(channel="chrome")`, so no browser download is needed. Unit tests don't cover `viewer.js` or `editor.js`.

## Architecture

**One renderer, two runtimes.** `src/quickdbd_cli/assets/render.js` is pure JS: it has no DOM access and returns strings. It holds:

- SVG rendering and geometry
- regions
- draw.io (mxGraph XML) export
- the dbt-style selector engine (`select`)
- the path finder and SQL `JOIN` generation

The browser page runs it directly. Python runs the same file inside embedded V8 via `jsrt.py` (mini-racer) for CLI exports, `--select`, `qdbd path` and `export --focus`. Put new rendering or selection logic in `render.js`, not Python, so the page and the CLI can't drift. Python calls globals such as `qdbdRenderSvg`, `qdbdSelect`, `qdbdFindPath` and `qdbd.regions`.

**jsrt quirks.** mini-racer's built-in `setTimeout` is broken. `jsrt.py` installs a synchronous timer queue (`__drain`) and polls promises. ELK needs `globalThis.global = globalThis` and must not see `self`. The runtime is a cached singleton, closed at exit.

**Pipeline** (`project.py` `Project.compile()` / `.build()`):

1. `parser.py`: per-file parse, then a global resolve, giving a `model.Schema`.
2. `measure.py` `model_json()`: plain-JSON model, with table/column widths taken from a committed Inter glyph-width table, so Python and the browser agree on sizes.
3. `layout.py`: positions.
4. `html.py`: the self-contained page (model JSON plus inline `render.js`, `viewer.js`, CSS and base64 fonts), or `export.py` (PNG via resvg-py with the bundled Inter TTFs).

**Parser fidelity is the #1 requirement.** `parser.py` mirrors QuickDBD's own JS parser (app bundle v2.4.427.0) step by step, including its error-message strings, identifier encoding (`encode()`: non-`[A-Za-z0-9_]` characters become their char code), and quirks such as the `..` placeholder never matching (encoding happens first).

- Deliberate deviations are warnings prefixed "QuickDBD would reject this:": tabs, `decimal(10, 2)`, `NOT NULL`, indented headers, `[layout]` entries for unknown tables. `--strict` turns them into errors.
- `default=` keeps its case; QuickDBD lowercases it.
- Don't "fix" QuickDBD behaviour without checking the spec in `docs/superpowers/specs/2026-10-17-qdbd-design.md`.
- Multi-file: all tables share one namespace, `CaseSensitive` applies to the file it's set in, and duplicate tables report both locations.

**Layout** (`layout.py`):

- The default is ELK `stress` followed by an ELK `sporeOverlap` pass (layered layouts produced very long edges), then a 90° turn if the result is tall (`_landscape`).
- Positions come from, in priority order: the sidecar `*.layout.json` (keyed by table **name**), then QuickDBD `[layout]`, then auto. New tables go next to their related tables via a spiral search (`place_missing`), and existing positions never move.
- `--by-group` lays out each group separately and packs the blocks.
- `qdbd build` never writes the sidecar; only `serve` and `qdbd layout` do. Running `qdbd serve examples/synthetic` and dragging rewrites the committed `examples/synthetic/qdbd.layout.json`; don't commit that by accident.

**Viewer** (`assets/viewer.js`): one IIFE over a state object `S`.

- `S.model` is the full model; `S.vm` is the filtered view model. Render, tree, minimap and exports use `S.vm`; details and links use the full model.
- Covers: focus/path highlighting, the explorer, the details panel, regions toggle, and URL-hash state (`f t p m r z c`) for shareable links.
- `editor.js` (CodeMirror 5 from cdnjs) is only loaded in `qdbd serve`.
- `serve.py` uses stdlib HTTP plus SSE with mtime polling. mtimes go over the wire as **strings**, because nanosecond ints overflow JS numbers. Stale writes return 409.

**Model JSON annotations** are optional keys that both renderers understand:

- `t.group` / `file` / `line`: explorer groups and regions
- `t.doc` / `c.doc`: tooltips
- `t.diff` and `model.diff`: from `diff.annotate_model`, for `build --diff-base`
- `model.regions`: set by `--by-group`
- `t.tags` / `t.color` and `model.tags` (legend): from `tags.py`. Tags come from `# @tag:` comments, else the name prefix (`dim_`, `fct_`, …), else `# @dbt-tags:`; `# @color TAG #hex` overrides colours. All are comments, so files stay valid QuickDBD. Diff colours win over tag colours

**Other modules:**

- `dbt.py`: manifest/catalog → QuickDBD text. PKs come from `unique` + `not_null` tests or constraints; FKs from `relationships` tests and `foreign_key` constraints. Constraint targets are resolved after collection. Output is self-checked by compiling it before anything is written.
- `diff.py`: schema diff by name. `--base` reads files with `git show REF:path`, with no checkout.

## Conventions

- **Determinism:** output must not contain timestamps or randomness (`elk.randomSeed`, sorted JSON). `test_build_is_deterministic…` asserts byte-identical builds.
- **Pip-only runtime:** no Node, Graphviz, Cairo or browser at runtime. Vendored assets need their licenses kept and listed in `NOTICE`: `elk.bundled.js` (EPL-2.0) and Inter (OFL).
- **Docs:** `mkdocs.yml` builds `docs/`, excluding `docs/superpowers/` (design specs). Theme overrides are in `overrides/` (custom header, breadcrumb) and `docs/stylesheets/extra.css` (modelith.sh-style). Screenshots in `docs/assets/img/` come from real builds.
- **CI:** `.github/workflows/ci.yml` runs ruff and pytest on macOS and Ubuntu with Python 3.11–3.13. `.github/workflows/erd.yml` dogfoods `action.yml` with `qdbd-version: source`: PR diff comment, then docs and demos deployed to Pages from `main`.
- **Releases:** bump `version` in `pyproject.toml` **and** `src/quickdbd_cli/__init__.py`, merge, then run `scripts/release.sh`. It reads `TWINE_USERNAME`/`TWINE_PASSWORD` from the gitignored `.env`, uploads to PyPI, tags `vX.Y.Z` and creates the GitHub release. There is no tag-triggered publish workflow.
- **Git:** work happens on branches with PRs into `main`. Commit messages and PRs carry no AI-attribution lines.
