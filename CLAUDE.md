# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`quickdbd-cli` (command `qdbd`, on PyPI) compiles QuickDBD-syntax `.txt` schemas, DBML (`.dbml`, or DBML in a `.txt`), or a dbt `manifest.json`, into an interactive single-file HTML ER diagram that stays usable at 200+ tables. It also exports PNG, SVG and draw.io, diffs schemas against a git ref, serves the schema to AI agents over MCP (`qdbd mcp`), and ships a composite GitHub Action (`action.yml`). The docs site (MkDocs Material) and live demos are published to GitHub Pages: docs at `/`, demos at `/demo/` and `/demo/jaffle/`.

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
cd vscode && npm ci && npm run typecheck && npm test   # extension: unit + grammar tests (Node 22+)
cd vscode && npm run test:integration                  # downloads VS Code, runs the extension in it
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

1. `parser.py`: per-file parse (`parse_file` picks the syntax with `syntax_of`; DBML goes to `dbml.py`), then a global resolve, giving a `model.Schema`.
2. `measure.py` `model_json()`: plain-JSON model, with table/column widths taken from a committed Inter glyph-width table, so Python and the browser agree on sizes.
3. `layout.py`: positions.
4. `html.py`: the self-contained page (model JSON plus inline `render.js`, `viewer.js`, CSS and base64 fonts), or `export.py` (PNG via resvg-py with the bundled Inter TTFs).

**Parser fidelity is the #1 requirement.** `parser.py` mirrors QuickDBD's own JS parser (app bundle v2.4.427.0) step by step, including its error-message strings, identifier encoding (`encode()`: non-`[A-Za-z0-9_]` characters become their char code), and quirks such as the `..` placeholder never matching (encoding happens first).

- Deliberate deviations are warnings prefixed "QuickDBD would reject this:": tabs, `decimal(10, 2)`, `NOT NULL`, indented headers, `[layout]` entries for unknown tables. `--strict` turns them into errors.
- `default=` keeps its case; QuickDBD lowercases it.
- Don't "fix" QuickDBD behaviour without checking the spec in `docs/superpowers/specs/2026-10-17-qdbd-design.md`.
- Multi-file: all tables share one namespace, `CaseSensitive` applies to the file it's set in, and duplicate tables report both locations.

**DBML** (`dbml.py`): lexer, statement scanner, interpreter, producing the same `FileParse` as `parser.py`, so mixed folders share one namespace and one resolve step.

- The reference is `@dbml/parse` 10.3.1 (holistics/dbml). Its snapshot tests are copied, reduced, into `tests/fixtures/dbml-ref` (`scripts/import_dbml_corpus.py`): valid files must compile to the reference's tables, columns, refs and groups; invalid ones must error on a reference line. Error wording is ours.
- Detection (`parser.syntax_of`): `.dbml`, or a `.txt` with a DBML top-level declaration (`Table x {`, `Ref:` + operator, ...). No valid QuickDBD file matches; `test_syntax_of_existing_files_stay_quickdbd` guards that. The extension mirrors it in `schema.ts` `looksLikeDbml`.
- Relationships carry per-end cards (`PendingRel.cards`), since DBML has 16 operators (`?` = optional side) and `REL_TYPES` 9. A composite ref is one `Relationship` per column pair.
- `TableGroup` → `Table.group` (beats the per-file group), `headercolor` → `Table.color` (beats tags, loses to diff), notes → `comments`. What isn't drawn (enums, checks, records, deps, ...) goes to `FileParse.unmodelled`.
- `convert.py` (`qdbd convert`) writes either syntax from a compiled schema; losses are warnings plus `lost` keys, and the CLI recompiles the output and compares `canonical()` before writing.

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
- `t.tags` / `t.color` and `model.tags` (legend): from `tags.py`. Tags come from `# @tag:` comments, else the name prefix (`dim_`, `fct_`, …), else `# @dbt-tags:`; `# @color TAG #hex` overrides colours. All are comments, so files stay valid QuickDBD. Diff colours win over tag colours.
- `c.color`: column tags (`# @tag:` on or above a column line) colour the row with the first tag's colour; `added`/`removed` default to green/red (removed is struck through).

**Other modules:**

- `dbt.py`: manifest/catalog → QuickDBD text. PKs come from `unique` + `not_null` tests or constraints; FKs from `relationships` tests and `foreign_key` constraints. Constraint targets are resolved after collection. Output is self-checked by compiling it before anything is written.
- `share.py`: `qdbd share` (refused unless `QDBD_ALLOW_SHARE=1`: a client's schema may not be allowed on GitHub; then it prints `DISCLAIMER` and asks `[y/N]`, or needs `--yes` with no terminal) publishes the built page as a gist via `gh api` (POST/PATCH `/gists`), remembering gist ids in `~/.cache/qdbd/shares.json` (`QDBD_CACHE_DIR` overrides; tests fake `subprocess.run`). `serve --read-only` renders the plain viewer plus `LIVE_JS` (SSE reload), omits file text from `/state`, returns 403 on writes, and never writes the layout file.
- `diff.py`: schema diff by name. `--base` reads files with `git show REF:path`, with no checkout. Refs starting with `-` are refused (they'd be git options); `merge_base()` gives a branch's fork point.
- `mcp.py` + `agent.py` + `targets.py`: `qdbd mcp`, a stdlib-only MCP stdio server.
  - `mcp.py` speaks both protocol eras: modern 2026-07-28 (stateless; a request is modern iff `params._meta` has `io.modelcontextprotocol/protocolVersion`; list/discover results need `ttlMs`/`cacheScope`) and legacy `initialize` (2024-11-05 to 2025-11-25; batches only for 2025-03-26). Stdout carries only protocol messages: `isolate_stdio` moves fd 1 to stderr and fd 0 to devnull before anything else runs, so never print to the wire. Requests run one at a time (jsrt/ELK aren't thread-safe).
  - `agent.py` holds the tools: plain functions over a `Workspace`, returning compact text under a 40k-character budget; failures are `ToolError` (an `isError` result the agent can act on). The `syntax_reference` tool serves `assets/syntax-reference.md`; update it when either syntax gains a feature. Tests call them directly; `tests/test_mcp.py` also drives the official `mcp` SDK client (a dev dependency only) in all three modes.
  - `targets.py` finds schema projects in a folder with the VS Code extension's rules (`target.ts`, `schema.ts`, the sidebar scan); keep them in step. `tests/fixtures/targets/cases.json` runs against both.

**VS Code extension** (`vscode/`, id `MarkPhamm.quickdbd`): TypeScript bundled by esbuild, no runtime npm deps. Published on the VS Code Marketplace and Open VSX (Cursor, Windsurf and VSCodium search Open VSX), with the `.vsix` also attached to each GitHub release.

- Two languages, `quickdbd` and `dbml` (`.dbml`, grammar `syntaxes/dbml.tmLanguage.json`); `isSchemaLanguage` / `LANGUAGES` in `checker.ts`, `schemaLanguage` in `target.ts` picks a `.txt` file's. **Convert to DBML / QuickDBD Syntax** wrap `qdbd convert` (`convert.ts`).
- It has no parser. Diagnostics, outline and go-to-definition come from `qdbd check --format json --symbols [--stdin-file F]`. The preview is `qdbd serve --embed --port 0` in an iframe inside a webview; **Compare with Git Ref** is the same preview with `--diff-base REF`. **Open in Browser** (`Previews.browse`) is plain `qdbd serve --port 0 --no-open` opened with `openExternal`: one server per target, reused, killed on deactivate. Export, HTML export and dbt import wrap `qdbd export` / `build` / `import dbt`.
- Nothing needs a terminal. When `qdbd` is missing or older than `MIN_VERSION`, `cli.ts` installs it into a venv in the extension's global storage (`venv.ts`: a Python 3.11+ found on the machine, else `uv venv --python >=3.11`). Resolution: `quickdbd.qdbdPath` (exclusive), then the workspace `.venv`/`venv`, then the newer of the extension's venv and `qdbd` on `PATH`; too-old ones are skipped.
- Share doesn't use `qdbd share`: it signs in with VS Code's GitHub auth (`gist` scope) and calls the gist API itself (`gist.ts`, over `node:https` so VS Code's proxy applies), mirroring `share.py`: same description, file name, links and `shares.json` cache/key, so the CLI and extension update one gist. Keep the two in step. Editors without a GitHub auth provider fall back to `qdbd share` (with `QDBD_ALLOW_SHARE=1` set for it). Sharing is off, and its menus and sidebar row hidden, until the user setting `quickdbd.allowSharing` (`scope: application`, so no workspace can turn it on) is true; each share then needs a modal disclaimer's **Share** (text kept in step with `share.py`), and the fallback passes `--yes` to qdbd 0.4.0+.
- The sidebar (`sidebar.ts`, Activity Bar container `quickdbd`): **Schemas** finds `*.txt` files with `isSchemaFile` (the same test as opening a file as QuickDBD), groups them by `findTarget`, and checks each from disk with `checker.checkTarget` (skipped while an editor has unsaved text in it), so outlines come from the same `check --symbols` report; column types/keys and table docs need qdbd 0.1.18+. **Actions** runs commands on `Sidebar.current()`. Commands resolve their schema in `extension.ts` `schemaDoc` (sidebar row, editor-title Uri, current, picker). Welcome views key on the `quickdbd.cliMissing` / `quickdbd.noSchemas` context keys. `activate()` returns a test API (`schemas()`).
- Embed messages (the bridge is in `viewer.js`): the page posts `qdbd.ready` and `qdbd.reveal {file, line}`; it receives `qdbd.focus {table}` (quiet: no details panel) and `qdbd.theme`.
- `src/schema.ts`, `target.ts`, `venv.ts`, `gist.ts` and `mcpdef.ts` don't import `vscode`, so `node --test` runs them directly (Node's type stripping: keep `.ts` import extensions and erasable syntax only).
- VS Code caches document symbols per document version, so providers `await checker.ready(doc)` before answering.
- `MIN_VERSION` in `src/cli.ts` is the oldest `qdbd` the extension accepts. Raise it when the extension starts using a new CLI flag. A feature only some users need gets its own floor instead, like `MCP_MIN_VERSION` (0.3.0) in `mcpdef.ts`.
- `mcp.ts` offers `qdbd mcp --root <folder>` to AI chat (`vscode.lm.registerMcpServerDefinitionProvider`, VS Code 1.101+, feature-detected with local types so `engines` stays at 1.85). `provideMcpServerDefinitions` is called eagerly in any workspace: it must stay silent and cheap (no qdbd lookup, no `qdbd check`); qdbd is found and version-checked in `resolveMcpServerDefinition`.
- Integration tests (`test/integration/`): the workspace is a scratch git repo (examples/ plus the jaffle fixture as a dbt project), so compare and import run for real. `QDBD_TEST_INSTALL=1` also installs `qdbd` from this checkout into the extension's venv (`QDBD_PIP_SPEC`); it only proves something when no new-enough `qdbd` is on `PATH`. Change text with `editor.edit` (and `restore()`), never the `undo` command: it acts on the focused editor, and nothing has focus while another app is in front, so it silently does nothing. `run.mjs` unsets `ELECTRON_RUN_AS_NODE`, which is set inside VS Code terminals. `QDBD_HOLD=ms QDBD_CDP=9333` keeps the window open with a DevTools port, so Playwright `connect_over_cdp` can screenshot it and evaluate inside the preview iframe.

**Demo gallery** (`/demo/`): `gallery/demos.toml` is the catalog. `scripts/build_gallery.py --out site/demo` builds each demo through the Python API (not the CLI, so titles and model paths are stable) plus the gallery page from `gallery/index.html`. Card images in `docs/assets/img/gallery/` come from `scripts/gen_thumbnails.py` (Playwright, dev-only) and must be regenerated when a demo changes. Demo sources live in `gallery/`, not `examples/`, because `examples/` ships in the sdist.

## Conventions

- **Determinism:** output must not contain timestamps or randomness (`elk.randomSeed`, sorted JSON). `test_build_is_deterministic…` asserts byte-identical builds.
- **Pip-only runtime:** no Node, Graphviz, Cairo or browser at runtime. Vendored assets need their licenses kept and listed in `NOTICE`: `elk.bundled.js` (EPL-2.0) and Inter (OFL).
- **Docs:** `mkdocs.yml` builds `docs/`, excluding `docs/superpowers/` (design specs). Theme overrides are in `overrides/` (custom header, breadcrumb) and `docs/stylesheets/extra.css` (modelith.sh-style). The home page (`docs/index.md`) is a landing page rendered by `overrides/home.html` + `docs/stylesheets/home.css`; the docs proper start at `docs/guide.md`. `hooks/gallery.py` feeds `gallery/demos.toml` to the templates. Screenshots in `docs/assets/img/` come from real builds.
- **CI:** `.github/workflows/ci.yml` runs ruff and pytest on macOS, Ubuntu and Windows with Python 3.11–3.13, plus a `vscode` job (typecheck, unit/grammar tests, integration under `xvfb-run`, `.vsix` artifact). `.github/workflows/erd.yml` dogfoods `action.yml` with `qdbd-version: source`: PR diff comment, then docs and demos deployed to Pages from `main`.
- **Releases:** bump `version` in `pyproject.toml` **and** `src/quickdbd_cli/__init__.py`, merge, then run `scripts/release.sh`. It reads `TWINE_USERNAME`/`TWINE_PASSWORD` from the gitignored `.env`, packages the extension (needs Node 22+ on `PATH`), uploads to PyPI, tags `vX.Y.Z` and creates the GitHub release with the `.vsix` attached. With `OVSX_PAT` in `.env` it then publishes the extension to Open VSX (`--skip-duplicate`, so unchanged versions are a no-op). The VS Code Marketplace is published by `.github/workflows/publish-vscode.yml` (`gh workflow run publish-vscode.yml`), which uses Marketplace Trusted Publishing (GitHub OIDC, no token; the policy lives on the publisher's **Trusted Publishing** tab). A `vsce` PAT would need an Azure subscription, and the web upload hangs when the browser blocks reCAPTCHA. The script prints a reminder when the Marketplace is behind. The extension's version (`vscode/package.json`, plus `vscode/CHANGELOG.md`) is bumped separately, only when the extension changes. There is no tag-triggered publish workflow.
- **Git:** work happens on branches with PRs into `main`. Commit messages and PRs carry no AI-attribution lines.
