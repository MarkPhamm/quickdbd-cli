# DBML support: design

## Why

The user's team writes schemas in two syntaxes. Some people use QuickDBD text (what qdbd reads today); others design in dbdiagram.io and send **DBML** (https://dbml.dbdiagram.io/docs/). A teammate's DBML file run through `qdbd check` today gives 19 errors: qdbd stops at `Table members {`.

The goal: qdbd reads DBML as it is, with no conversion step, everywhere it reads QuickDBD. When the teammate sends a new version next week, the user drops it in and rebuilds. Converting between the two syntaxes is also wanted, as a separate command, for people who want to move a schema from one side to the other.

## Goals

1. **DBML is a first-class input.** `check`, `build`, `serve`, `export`, `path`, `diff`, `share`, `layout` and the GitHub Action all accept DBML files, and produce the same kind of output as for QuickDBD.
2. **Detection by content.** `.dbml` files are always DBML. A `.txt` file holding DBML (the teammate's files sometimes arrive as `.txt`) is read as DBML too. Everything else stays QuickDBD.
3. **Mixed projects.** One folder can hold QuickDBD files and DBML files. All tables share one namespace, as multi-file QuickDBD does today: a DBML `Ref` can point at a table defined in a QuickDBD file and the other way round, and a table defined in two files is the usual duplicate-table error naming both places. Each file is one syntax; a file never mixes them.
4. **Accept everything dbdiagram.io accepts.** A file that dbdiagram.io accepts never errors in qdbd. A file it rejects errors in qdbd too, on the same line (wording can be qdbd's own).
5. **Conversion both ways:** `qdbd convert` (see below), lossless for everything the target syntax can express, with a warning for everything it can't.
6. **VS Code extension** handles DBML like QuickDBD: highlighting, errors, outline, go-to-definition, sidebar, preview, Compare with Git Ref, export, plus convert commands.
7. **`qdbd serve` browser editor** edits DBML with DBML highlighting.
8. **A DBML demo in the gallery** (`/demo/`).
9. **Docs** for all of the above.

## Non-goals

- Fixing `qdbd path` to emit one multi-column `JOIN` for composite keys. Today parallel links between two tables produce a JOIN on only one of the columns; DBML composite refs will inherit that. It's a separate follow-up that also helps QuickDBD files.
- Drawing enums, indexes beyond the badges below, checks, sample records, `Project` settings, sticky notes, or ref `delete`/`update`/`color` settings. They are parsed and accepted, not drawn.
- DDL/SQL output from DBML.
- Mixing both syntaxes inside one file.

## Anti-goals (a failure even if it "works")

- A file dbdiagram.io accepts errors or loses tables, columns or links in qdbd.
- An existing QuickDBD file behaves differently: detected as DBML, new warnings, or a build that's no longer byte-identical. Every file under `examples/` and `gallery/` must build exactly as before.
- `qdbd convert` drops something silently. Every loss is a warning.
- Any new runtime dependency (Node, a JS DBML parser bundle, etc.). Still pip-only.
- The teammate's real schema ends up in this public repo. Tests and the demo use invented schemas.

## Decisions

### Made by the user

| Topic | Decision |
|---|---|
| Workflow | Read DBML natively; the DBML file stays the source of truth |
| Detection | By content, so DBML saved as `.txt` works |
| Mixed syntaxes | Both kinds of file in one project |
| Composite `Ref` | One link per column pair: `(a, b, c) - (a, b, c)` draws 3 lines, the same as a composite FK hand-written in QuickDBD |
| Scope additions | Gallery demo and conversion both included |

### Made by Claude (the user can override)

| Topic | Decision |
|---|---|
| Parser | A new hand-written Python module (`dbml.py`) next to `parser.py`. Not `@dbml/core` in mini-racer: it's a large bundle that also ships SQL importers, and the rest of the pipeline is Python |
| Fidelity reference | `@dbml/parse` **10.3.1** (github.com/holistics/dbml `packages/dbml-parse`, the current stable npm release; 10.4/11.0 are alphas). Its single-file DBML test inputs are the acceptance corpus (Apache-2.0: list it in `NOTICE` if fixtures are copied). Its multi-file module tests are out (see `use` below) |
| `use` / `reuse` (DBML modules) | Not resolved: qdbd already reads every file it's given into one namespace, and dbdiagram.io reportedly doesn't resolve `use` either. A plain `use`/`reuse` is a warning ("qdbd ignores `use`; pass the imported file or its folder too"). An import that renames (`as`) is an error, since it needs per-file scopes qdbd doesn't have |
| Other 10.3.1 syntax | `Dep` lineage (all forms), `Metadata` blocks, custom properties, `DiagramView`, `[inactive]` refs and `TableGroup` colours: parsed and validated, not drawn; `convert` warns. `Dep` edges are not links and never reach the path finder |
| Release safety | Two fixes. (1) `scripts/release.sh` refuses to run when there are untracked files under the sdist's `include` paths: two untracked files under `examples/` went out in the 0.1.18 and 0.1.19 sdists. (2) Anchor the sdist `include` patterns in `pyproject.toml` (`/src`, `/tests`, `/examples`, `/scripts`): unanchored, `src` and `scripts` also match `vscode/node_modules/**/src` and `vscode/.vscode-test/**`, so 0.1.16–0.1.19 sdists carried ~930 ignored files (hatch only reads the root `.gitignore`). A test lists the built sdist and fails on anything outside the expected paths |
| Pipeline | The DBML parser produces the same per-file intermediate as `parser.py` and joins the same global resolve step, so cross-file links, aliases and duplicate-table errors work identically for both syntaxes |
| `TableGroup` | Becomes the table's explorer group and `--by-group` region. Tables outside any group fall back to today's per-file group |
| `headercolor` | Becomes the table colour; beats tag colours, loses to diff colours |
| Tags | Name-prefix tags work as today. `// @tag:` directly above a `Table` line and `// @color TAG #hex` anywhere work like their `#` forms. Plain `//` comments are not docs (DBML uses `note`) |
| Notes | Table `Note`/`note:` and column `note:` become docs (tooltips, details panel). Multi-line `'''` notes keep their line breaks |
| Names | `core.users` displays as `core.users`; `public.users` and `users` are the same table (`public` is DBML's default schema). Case sensitivity follows the reference parser |
| Version | qdbd 0.2.0; extension 0.4.0 with `MIN_VERSION` raised to 0.2.0 |

## How DBML maps onto the model

The model (`model.py`) is unchanged except where noted. `Column`/`Table`/`Relationship` already cover most of DBML.

| DBML | Model |
|---|---|
| `Table name as alias [headercolor: #hex, note: '…'] { … }` | `Table`, `aliases`, colour, doc |
| column `name type [settings]` | `Column.name`, `Column.type` as written (`varchar(255)`; `"double precision"` unquoted) |
| `pk` / `primary key` | `pk` |
| `null` | `nullable = True` (the NULL badge) |
| `not null`, or nothing | `nullable = False`. DBML columns are nullable when unspecified, but dbdiagram shows no badge for them, so neither does qdbd |
| `unique` | `unique` |
| `increment` | `identity` |
| `default: …` | `default`, case kept, DBML's quotes/backticks removed (so `default=CURRENT_TIMESTAMP` round-trips through `` default: `CURRENT_TIMESTAMP` ``) |
| `note: '…'` | column doc |
| `ref: > t.c` (inline) | a `Relationship`, same as a top-level `Ref` |
| `indexes { col [pk] }`, composite `(a, b) [pk]` | `pk` on each column |
| `indexes { col [unique] }` (single column) | `unique` |
| other index entries (composite unique, plain, expression) | `index` badge on each named column; expressions ignored |
| `Ref: a.x > b.y` / `<` / `-` / `<>` | `Relationship` with cards many/one, one/many, one/one, many/many |
| optional sides `-?`, `?-`, `?-?`, `<?`, `?>` | the zero-or variants `-0`, `0-`, `0-0`, `-0<`, `>0-` (confirm each direction against 10.3.1) |
| composite `Ref: a.(x, y) > b.(x, y)` | one `Relationship` per column pair; error if the counts differ |
| `Ref` long form with a name and settings | same; name and settings ignored |
| `TableGroup g { … }` | new optional `Table.group`, used by `measure._groups` before the per-file fallback |
| `TablePartial` + `~partial` | expanded into the table (local columns win, then the last partial injected) |
| `Enum`, `checks`, `records`, `Project`, sticky `Note` | parsed, validated, not drawn |

FK flags follow today's rule (`post_process`): every non-PK column at either end of a link is an FK.

## Detection

- `.dbml` → DBML.
- `.txt` → DBML when the file contains a DBML top-level declaration: a line starting with `Table`, `Enum`, `TableGroup`, `TablePartial`, `Project` or `Records` followed by a name and `{`, or `Ref` followed by an optional name and `:` or `{` (keywords case-insensitive, as in DBML). Otherwise QuickDBD.
- Decided from the whole file, not the first line, so one broken line (the user's paste began `/ Use DBML…`, one slash) still gives DBML errors on that line instead of 19 confusing QuickDBD ones.
- The rule has to be strict enough that no existing QuickDBD file flips (a QuickDBD header can't contain `{`, so this should hold; prove it with every `.txt` under `examples/`, `gallery/` and `tests/`).
- The same rule is mirrored in the extension (`schema.ts`, next to `looksLikeQuickdbd`) and in file discovery.

## Where DBML has to be wired in

- `project.discover`: folders pick up `*.dbml` as well as `*.txt`. Error text "no .txt schema files" mentions both.
- `diff.py`: `--base` file listing includes `.dbml`.
- `measure._groups`: strips `.dbml` like `.txt`; honours `Table.group`.
- `check --symbols`: tables, columns, types, keys, docs and line ranges for DBML too (the extension's outline and sidebar need them).
- `serve`: writes DBML files back unchanged; CodeMirror DBML mode in `editor.js` (CodeMirror 5 has none upstream, so a small `simple` mode).
- `--strict` and the "QuickDBD would reject this" warnings stay QuickDBD-only.
- `[layout]` doesn't exist in DBML; the sidecar `*.layout.json` works as today.
- `action.yml`: check whether its file globs need `.dbml`.

## `qdbd convert`

```
qdbd convert PATH... --to dbml|quickdbd [-o FILE_OR_DIR]
```

- One output file per input file, same base name with the new extension (`.dbml` / `.txt`). With one input and no `-o`, print to stdout. With `-o DIR`, write into it keeping relative paths.
- Inputs already in the target syntax are copied unchanged (so a mixed folder converts cleanly).
- The output is compiled before anything is written (like `dbt.py`) and must produce the same tables, columns, keys and links as the input, **after removing everything a warning reported as lost** (and ignoring zoom/position). If it doesn't, that's a bug: exit non-zero and write nothing.
- Every loss is a warning naming the line, e.g. `warning: index (a, b) [unique] has no QuickDBD equivalent; marked INDEX on both columns`.
- Round-trip test: every QuickDBD example and gallery demo converted to DBML and back gives the same model, minus warned losses. In practice the only ones in today's examples are table-level links (`examples/quickdbd-sample.txt`, `examples/synthetic/{sales,marketing,inventory}.txt`).

QuickDBD → DBML:

- `#` doc comments → `Note`/`note:`; other comments → `//`.
- `# @tag:` / `# @color` → `// @tag:` / `// @color`.
- All nine relationship types have a DBML operator (the zero-or variants via `?`), so links convert without loss.
- Table-level links (`rel >- Other`) have no DBML form: warning, and kept as a plain `//` comment (no qdbd-only directive, so the DBML file means the same in qdbd and dbdiagram.io).
- `[layout]` positions go into the layout sidecar next to the output (existing sidecar entries win); `[settings]` → warning.
- `NULL` → `null`; no `NULL` → nothing (so the diagram looks the same both ways).

DBML → QuickDBD:

- Notes → `#` doc comments, one per line.
- `TableGroup`: with `-o DIR`, one `.txt` per group (ungrouped tables stay in a file named after the source), so the explorer groups survive; to a single file, a warning.
- `headercolor`: warning, dropped.
- Enums → a `#` comment listing the values above the first table that uses them.
- Composite/expression indexes, checks, records, `Project`, sticky notes, ref settings → warning, dropped.
- Composite refs → per-column `FK` lines.

## VS Code extension

- `.dbml` files and DBML `.txt` files get a DBML language and TextMate grammar. Other DBML extensions may also claim `.dbml`; the builder picks the language id (sharing the common `dbml` id is the friendlier choice) and makes sure diagnostics, outline, preview and the sidebar still work when another DBML extension is installed.
- Sidebar **Schemas** lists `.dbml` files alongside `.txt`.
- New commands: **Convert to DBML** and **Convert to QuickDBD**, wrapping `qdbd convert`, opening the result.
- `MIN_VERSION` → 0.2.0; extension `CHANGELOG.md`; integration test workspace gets a DBML file and a mixed folder.

## Gallery demo

- An invented schema written in DBML (not the teammate's), around 25 tables in 4 `TableGroup`s, using notes, an enum, a composite `Ref`, `headercolor` and a schema-qualified name, so the card shows what DBML adds. Domain is the builder's call; it shouldn't repeat one already in the gallery.
- New gallery group "DBML schemas". `demos.toml` `source` accepts `.dbml` files and folders; card thumbnail from `scripts/gen_thumbnails.py`.

## Docs

- New page **3.2 DBML** under Schema Files (renumber the rest): what's supported, what's drawn vs accepted, detection, mixing with QuickDBD, `qdbd convert` and its losses.
- Touch `syntax.md` (pointer to DBML), `files.md` (mixed folders), `cli.md` (`convert`), `vscode.md`, README, and `CLAUDE.md` (architecture: the DBML parser and detection).

## Done when

- The teammate-style file (tables, `pk`, `not null`, quoted `"tables"`, many-to-one refs, a 3-column composite one-to-one) builds from both `team.dbml` and `team.txt` with no errors, and the composite ref draws 3 links.
- The reference parser's valid DBML inputs all compile; its invalid ones error on the same line.
- Every existing example and gallery demo builds byte-identical to before.
- Mixed folder: a QuickDBD FK to a DBML table and a DBML `Ref` to a QuickDBD table both resolve.
- Round-trip conversion holds for every example and demo, minus warned losses.
- `release.sh` refuses to release with untracked files under the sdist paths.
- Ruff, pytest, `mkdocs build --strict` and the extension's unit, grammar and integration tests pass; a real-browser check of `serve` editing a DBML file.
- Released: PyPI 0.2.0, extension 0.4.0 (Open VSX by script, Marketplace by manual upload), gallery and docs deployed.

## Left to the builder

- Module layout inside `dbml.py`, the lexer/parser technique, and error wording.
- Exact detection regex, within the rule above.
- The gallery demo's domain and content.
- The extension's language id and grammar details.
- Task order and how to split the work into PRs.
