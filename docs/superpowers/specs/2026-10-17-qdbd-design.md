# quickdbd-cli (`qdbd`): design + build plan

## Context

QuickDBD (app.quickdatabasediagrams.com) turns a small text syntax into ER diagrams, but the free tier caps at 10 tables: from table 11 on, tables are renamed "Table N" and their columns become "...". We want an open-source CLI that compiles **the same syntax** into an **interactive HTML diagram** with no table cap, comfortable at ~200 tables.

It gets used three ways:
- hand-writing schemas
- pasting existing QuickDBD schemas that hit the 10-table wall
- committing `.txt` files to a repo and regenerating diagrams in CI

**Worst failure (user's words, ranked #1):** a schema that works in QuickDBD fails or renders differently here.

Repo state: empty (Apache-2.0 `LICENSE`, Python `.gitignore`, one commit on `main`).

## Goals

1. Parse 100% of valid QuickDBD syntax, with the same error messages, line-numbered.
2. `qdbd build`: one HTML file you can share, with QuickDBD's look, curved lines and table positions locked.
3. `qdbd serve`: live local editing. The page reloads when you save in your own editor, there's a browser editor pane with autosave, and dragging a table saves its position to a sidecar file.
4. `qdbd export`: PNG/SVG of a table plus its neighbours, for docs and PRs.
5. Multiple `.txt` files (or a folder) compile into one diagram, with foreign keys allowed across files.
6. `pip install` only: no brew/apt dependencies. Public on PyPI as `quickdbd-cli`, command `qdbd`.

## Non-goals (v1)
- SQL DDL export
- importing from a live database
- Windows support (must run on macOS; Linux runs in CI but isn't a promise)
- doc-comment tooltips
- dark mode
- JSON or GitHub-annotation output from `check`
- a reusable GitHub Action
- 1000+ table scale (target ~200)
- grouping or colouring by file

## Anti-goals (fail even if it "works")
- A valid QuickDBD file errors or loses data here.
- Install needs anything beyond pip (Graphviz, Cairo, Node, a browser).
- `serve` clobbers the file the user has open in their editor.
- The CLI phones home, or leaves timestamps/randomness in its output, so CI diffs are noisy.

## Decisions made by the user

| Topic | Decision |
|---|---|
| Output | Interactive HTML page |
| Positions | Auto-layout first, then drag in `serve`; saved to a **sidecar** `*.layout.json`, not into the `.txt` |
| Language | **Python 3.11+**, pip-only |
| Layout engine | **ELK**, run inside Python via the `mini-racer` wheel (bundled V8) |
| Lines | Curved, QuickDBD style |
| Look | QuickDBD look-alike (blue headers, key icon, types right-aligned), light only |
| Multi-file first layout | By relationships only, no per-file regions |
| Navigation | Search & jump, minimap, focus mode, collapse |
| Collapse | Global three-way toggle: full / keys only / header only |
| Editing in `serve` | Both your own editor and a browser editor pane; **autosave ~1s after typing stops** |
| Strictness | **Forgiving + warnings**: accept what QuickDBD rejects only where it's unambiguous, and warn |
| FK to a missing table/field | **Error, exit 1** (QuickDBD's message) |
| Image export | CLI `--focus Table --depth N`, plus PNG/SVG export buttons in the page |
| Table details | Cardinality markers, column badges (NULL/UNIQUE/INDEX/IDENTITY/default), FK hover highlight |
| Shared (built) HTML | **Locked**: pan, zoom, search, focus, collapse; no dragging |
| Internet | Allowed (CDN OK), not required |
| New table when a layout exists | Placed in free space **next to its related tables**; nothing else moves |
| `check` output | Human-readable only |
| CI support | README snippet + **pre-commit hook** |
| Audience / name | Public on PyPI, `quickdbd-cli`, command `qdbd` |
| Test data | Synthetic 200-table schema, generated |
| Parser proof | Hand-built test corpus (no running QuickDBD's code) |
| Deadline / builder | None; Claude builds end to end |
| Folder input | All `*.txt` under it, recursive |
| Source text in shared HTML | No, diagram only |

## Syntax spec (from QuickDBD's shipped parser, app bundle v2.4.427.0)

**File and sections**
- Lines split on `\r?\n`. A blank line ends a table.
- Optional sections come in this order, each at most once: `[tables]`, `[settings]`, `[layout]`.

**Tables**
- Header: `Name [as alias[, alias2]]`. Names containing a space or `.` must be double-quoted.
- Separator: a line of hyphens only, of any length.
- The only line allowed between the header and the separator is `rel [op] Target[.Field]`. With no operator it defaults to `-`.

**Columns**
- Grammar: `name` followed by any of these tokens, in any order, case-insensitive:
  - `PK`
  - `FK [op Target.Field]`
  - `NULL` / `NULLABLE`
  - `UNIQUE`
  - `INDEX`
  - `IDENTITY` / `AUTOINCREMENT`
  - `default=value`
  - the type: the first token that isn't a keyword
  - `type=default`, e.g. `string="a b"`
- Invalid combinations: PK+UNIQUE, PK+INDEX, UNIQUE+INDEX.
- Composite PK means `PK` on several columns.
- A field named only with dots (`.`, `..`) is a placeholder row.

**Relationships**
- Operators: `-`, `-<`, `>-`, `>-<`, `-0`, `0-`, `0-0`, `-0<`, `>0-`.
- A target may use an alias. Leaving out the field makes it a table-level relationship.
- More than one `.` is an error. Duplicate relationships, in either direction, are an error.

**Comments**
- `#` starts a comment unless it's inside quotes.
- Comment lines directly above a table or column, plus a comment at the end of its line, become its documentation (parsed and kept, not shown in v1).

**Settings and layout**
- `[settings]`:
  - `Zoom 10–200` sets the initial zoom.
  - `CaseSensitive on|off` controls whether lookups ignore case (they do by default).
  - `DefaultFieldType` is used for columns with no type.
  - `Position x y` is applied as the initial viewport position.
- `[layout]`: one line per table, `TableName x y`. Used as initial positions when the sidecar has no entry for that table.

**Errors**
- QuickDBD's messages, verbatim, formatted as `path:line: error: <message>`. Warnings use `warning:`.
- A clean `check` prints `No errors found. Good job!`. Errors exit 1; warnings alone exit 0, or exit 1 with `--strict`.

**Forgiving deviations (each one warns "QuickDBD would reject this")**
- Tabs.
- Spaces inside a type's parentheses (`decimal(10, 2)`).
- An explicit `NOT NULL` (treated as a no-op).
- `default=` keeps its original case. QuickDBD lowercases it; that's a rendering difference, not a rejection, so no warning.
- Anything ambiguous stays an error. For example, unquoted `dbo.Customer` would clash with `Table.Field` references.

**Multi-file**
- All tables and aliases share one namespace.
- A table defined in two files raises `Table 'X' already defined`, naming both locations.

**Multi-file settings and layout** (my call; each file stays valid QuickDBD on its own)
- `DefaultFieldType` applies only to the file that sets it.
- `CaseSensitive` applies to references written in the file that sets it. A reference from a case-insensitive file into a case-sensitive one matches ignoring case.
- `Zoom` and `Position` come from the first file, in sorted order, that sets them. A different value in a later file is a warning.
- A `[layout]` line may name a table from any file. If the table doesn't exist anywhere, that's a warning (QuickDBD's behaviour here is unverified).

**Error messages** (QuickDBD's verbatim strings, pulled from its shipped parser; `messages.py` holds exactly these):
- `Table name not defined`
- `Table 'X' already defined`
- `Table field name cannot be empty`
- `Table field 'X' already defined`
- `Unrecognized keyword 'X'`
- `Invalid relationship description (allowed: …)`
- `Relationship key cannot be empty`
- `Unknown relationship param`
- `Invalid relationship, the table/field '…' does not exist`
- `Multi-nested relationships are not allowed`
- `Relationship already defined at line N`
- `Invalid table name (use double quotes)`
- `Unrecognized table metadata`
- `Whitespace expected, tab character found`
- `Invalid section name`
- `Section '[x]' is out of order` / `already defined`
- `Layout definition requires 3 values (tableName, x, y)`
- `Invalid X/Y coordinate`
- `Setting key/value missing`
- `Invalid 'Zoom' value`
- `Invalid 'CaseSensitive' value`

Error messages for the invalid modifier combinations (PK+UNIQUE etc.) and for `NOT NULL` weren't captured verbatim. In phase 1, the builder re-reads QuickDBD's public in-app DOCS page to get them, and to confirm the `"FieldName, FieldType"` case and how a quoted `"dbo.Customer"` is written as an FK target.

**Corpus sources (my call):**
- Cases are written from the spec and the docs' described behaviour.
- `examples/quickdbd-sample.txt` is our own schema covering the same features as QuickDBD's demo, not a copy of theirs.
- **Known residual risk:** there are no real-world golden files. Any mismatch found later becomes a new corpus case.

## Architecture

```
.txt files ──parse──▶ AST + diagnostics ──resolve──▶ Schema model
                                                     │
              font width table ──measure──▶ table box + row sizes
                                                     │
  sidecar.layout.json ─┐                             ▼
  [layout] section ────┴──▶ positions ◀── ELK (mini-racer) for missing / --reset
                                                     │
                          render.js (pure: model+positions+opts → SVG string)
                         ┌───────────────┼──────────────────┐
                 build: HTML        serve: same page     export: render.js in
                 (viewer.js,        + drag/save +        mini-racer → SVG →
                  locked)           editor + reload      resvg → PNG
```

**Key design choice:** one renderer, `render.js`. It is a pure JavaScript function that produces an SVG string. The browser runs it, and Python runs the same file inside mini-racer for CLI exports. So the page, the SVG and the PNG can't drift apart, and the viewer re-renders on collapse or focus without needing a second renderer in Python.

### Package layout (`src/quickdbd_cli/`)

| Module | Responsibility |
|---|---|
| `cli.py` | argparse entry point `qdbd` with `check`, `build`, `serve`, `export`, `layout` |
| `parser/lexer.py`, `parser/parser.py` | Line tokenizer (quote-aware, `#` comments) → AST with line/col; QuickDBD error strings in one `messages.py` |
| `model.py` | Dataclasses: `Schema`, `Table`, `Column`, `Relationship`, `Diagnostic`, `SourceLoc` |
| `resolve.py` | Merge files, alias and case-insensitive resolution, missing-target and duplicate checks |
| `measure.py` | Text widths from a committed per-glyph width table for the bundled font (generated once by `scripts/gen_font_metrics.py` with fontTools as a dev-only dependency) → table width and row heights |
| `layout/elk.py` | Builds the ELK graph (nodes = tables, ports = column rows, layered, direction RIGHT, fixed `randomSeed`) and runs vendored `elk.bundled.js` in mini-racer |
| `layout/place.py` | Places new tables: centroid of related placed tables, then a spiral search for the nearest non-overlapping free spot. Pure Python and deterministic |
| `layout/sidecar.py` | Reads and writes `*.layout.json`: `{"version":1,"tables":{name:{x,y}}}`, sorted keys, integer coords, atomic write. Prunes deleted tables |
| `jsrt.py` | One shared mini-racer context: loads ELK and render.js, calls functions with JSON in and out |
| `html.py` | Writes the self-contained HTML: inline model+positions JSON, `render.js`, `viewer.js`, CSS, base64 woff2 font. Deterministic output |
| `serve.py` | stdlib `ThreadingHTTPServer` on 127.0.0.1; endpoints `/`, `/model`, `/events` (SSE), `POST /layout`, `GET/PUT /file`; mtime polling every 300 ms; opens the browser |
| `export.py` | Focus subgraph (BFS to `--depth`, default 1) → re-layout of that subset → SVG; PNG via resvg with the bundled font |
| `assets/` | `render.js`, `viewer.js`, `editor.js`, `style.css`, `elk.bundled.js` (EPL-2.0, unmodified, with its license file), font + license, CodeMirror 5 (MIT, vendored single file, serve-only) |

### Visual reference (user's QuickDBD screenshot)
After approval, the screenshot is copied to `docs/superpowers/specs/assets/quickdbd-reference.png`. Approximate values at 100% zoom:

**Canvas and tables**
- Canvas: very light grey (~`#f4f5f4`).
- Table: white body, ~205px wide (sized to its content), no visible border.
- Header: ~52px tall, solid blue (~`#2b5797`), white table name at ~18px.
- Rows: ~33px tall. Column name on the left, type right-aligned in light grey (~`#999`).

**Row styles**
- PK row: name bold and blue, grey key icon just before the type.
- FK row: name bold and dark.
- Other rows: regular dark text.

**Lines**
- Thin (~1px) light-grey (~`#bbb`) curves.
- Small crow's foot at the "many" end, small bar at the "one" end, sitting just outside the row edge.

**Zoom controls**
- Top right: `−`, `100%`, `+`, then a centre/fit icon.

**Not reproduced**
- The grey connection dots on the row edges. They are QuickDBD's tools for drawing relationships in its editor.

### Viewer behaviour (`viewer.js`, vanilla JS, no build step)

**In every mode**
- Pan by dragging the background. Zoom with the wheel or pinch, the −/+ buttons, the % readout and fit-to-screen, like the screenshot.
- Search box: substring match on table names and aliases. Picking a result zooms to the table and briefly flashes it.
- Minimap in the bottom-right corner, with a draggable viewport box.
- Focus: click a table and it plus its direct neighbours stay at full opacity while everything else fades to ~15%. Esc or clicking the background clears it.
- Collapse toggle (full / keys / header). In keys mode, PK, FK and related columns stay visible. When a column is hidden, its lines attach to the table header.
- Hovering a column highlights its lines and the target columns.
- Export PNG/SVG buttons save the whole diagram in its current collapse/focus state.

**Lines and markers**
- Curved cubic béziers from the side of the source row to the side of the target row. Each end picks left or right based on where the two tables sit relative to each other.
- Cardinality markers: a bar for one, a crow's foot for many, a circle for zero.

**Built HTML:** no dragging.

**`serve` only**
- Dragging a table updates the transform and its lines live. On drop it sends `POST /layout`, and the server writes the sidecar.
- Collapsible editor pane on the left, with one tab per file, a QuickDBD syntax-highlighting mode, autosave 1 s after typing stops, and an error panel underneath.
- If the file changes on disk while the buffer has unsaved edits, a banner offers *keep mine* / *reload*.
- When the files have errors, the last good diagram stays on screen alongside the error panel.
- On reload, the viewport and the collapse/focus state are kept.

### CLI surface

```
qdbd check  PATH... [--strict]
qdbd build  PATH... -o diagram.html [--layout FILE]
qdbd serve  PATH... [--port 8765] [--layout FILE] [--no-open]
qdbd export PATH... --focus TABLE [--depth 1] -o out.png|out.svg [--layout FILE]
qdbd layout PATH... --reset [--layout FILE]     # fresh ELK layout → sidecar
```

**PATH**
- A file, or a directory: all `*.txt` files under it, recursively, in sorted order.
- Default sidecar for a single file: `schema.txt` → `schema.layout.json`.
- Otherwise: `<common parent>/qdbd.layout.json`.

**Shared by all commands**
- `build`, `export` and `serve` run `check` first. Errors print and exit 1.
- `build` doesn't write the sidecar. Tables without a saved position are placed in memory, so CI builds never touch the working tree.

## What "renders differently" means (my call; check this one first)
**Must match QuickDBD:**
- every table, alias and column name
- column order within each table
- types (exactly as written)
- PK/FK/NULL/UNIQUE/INDEX/IDENTITY flags
- default values
- every relationship's two endpoints and cardinality

**Allowed to differ:**
- table positions (our auto-layout)
- which side of a row a line leaves from
- pixel styling
- `default=` letter case (we keep what you wrote; QuickDBD lowercases it)

The corpus and snapshot tests check the "must match" list.

## Calls I made (flagged for review)
- A single JS renderer, shared by browser and CLI export.
- The sidecar's name and location, as above.
- `--strict` turns warnings into errors.
- `export` without `--focus` exports everything. It falls out of the same code for free.
- argparse rather than click.
- The SSE server uses stdlib with mtime polling, so there's no watchdog dependency.
- CodeMirror 5 is vendored for the editor, to avoid a JS build toolchain.
- Font: an OFL UI font close to QuickDBD's, embedded as a woff2 subset.
- Build backend: hatchling.
- Linting: ruff.
- Project CI: GitHub Actions on macOS and Ubuntu, Python 3.11–3.13.
- Releases: PyPI trusted publishing, triggered by a tag.
- Work happens on a feature branch, not `main`. Commits carry no AI attribution (per your CLAUDE.md).

## Left to the builder
- ELK option tuning (spacing, node placement strategy, component packing). Tune against the synthetic 200-table schema, with a screenshot review checkpoint.
- Exact visual measurements, matched to the screenshot.
- The minimap implementation (SVG vs canvas).

## Build order (core first, each phase usable on its own)

0. **Dependency spike (~1 hour, throwaway).** The research check on these didn't finish, so prove them before anything else, in a fresh macOS venv:
   - `mini-racer` installs from a wheel.
   - `elk.bundled.js` runs inside it and lays out a 200-node graph in under 3 s. If ELK needs `setTimeout` or a Worker, shim it, or call the synchronous `elk-worker` dispatcher.
   - A pip-only resvg binding renders an SVG with a bundled font to PNG.
   - **If ELK can't run:** stop and come back to you. The fallback is a pure-Python layered layout, a trade-off you'd need to approve.
1. **Scaffold + parser + `qdbd check`.** `pyproject.toml`, src layout, pytest, ruff, CI. Test corpus in `tests/corpus/` (~100 cases: the docs examples, the demo sample, every error message, every quirk, every operator), each `.txt` with an expected `.json`.
2. **Resolve + multi-file + measure.** Cross-file references, duplicate detection, case sensitivity. Plus `scripts/gen_schema.py`, a deterministic generator for a synthetic 200-table schema across 5 files that uses every syntax feature, committed under `examples/`.
3. **Layout.** Vendor ELK, add the mini-racer bridge, the sidecar, `[layout]` import, new-table placement and `qdbd layout --reset`.
4. **`render.js` + `qdbd build` + viewer features.** Snapshot tests on the SVG output.
5. **`qdbd export`** (focus, SVG, PNG via resvg).
6. **`qdbd serve`** (reload, drag-save, editor pane, autosave, conflict banner).
7. **Release prep.** `.pre-commit-hooks.yaml` (`qdbd-check`), README with a GitHub Actions + GitLab CI snippet, release workflow, `NOTICE` covering ELK, CodeMirror and the font.

After you approve this plan:
1. I save it as `docs/superpowers/specs/2026-10-17-qdbd-design.md` and commit it.
2. `superpowers:writing-plans` expands it into a task-level plan.
3. Implementation is test-first.

## Verification
1. `pytest`: parser corpus, resolve, sidecar round-trip, placement doesn't overlap, ELK determinism, SVG snapshots, export.
2. `qdbd check examples/quickdbd-sample.txt` prints `No errors found. Good job!`. A broken file prints `path:line: error: …` and exits 1.
3. `qdbd build examples/synthetic/ -o /tmp/d.html` twice, then `cmp` the two outputs, which must be byte-identical. Then open the page and check search, minimap, focus, the three collapse modes, FK hover and the export buttons (headless screenshot via the `run` skill).
4. `qdbd serve examples/synthetic/`:
   - Edit a file in an external editor and the page reloads.
   - Drag a table and the sidecar diff shows just that table.
   - Type in the browser pane and the `.txt` updates after 1 s.
   - Add a new table and it appears beside its related tables.
5. `qdbd export examples/synthetic/ --focus Customer --depth 1 -o /tmp/c.png`: open the PNG and check the text renders in the bundled font.
6. Fresh venv: `pipx install .` on macOS with no brew packages, then run steps 2–5.
7. Performance on the 200-table schema: `build` in under 5 s on an M-series Mac, smooth pan and zoom, `serve` reload in under 1 s.
