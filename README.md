# quickdbd-cli (`qdbd`)

Compile [QuickDBD](https://www.quickdatabasediagrams.com)-syntax schema files into **interactive HTML ER diagrams**, with no table limit, from the command line. Built to stay readable at 200+ tables.

```
Customer
-
CustomerId PK int
Name string

Order
-
OrderId PK int
CustomerId int FK >- Customer.CustomerId
```

```bash
pipx install quickdbd-cli        # or: uvx --from quickdbd-cli qdbd ...
qdbd build schema.txt -o schema.html
```

**Docs:** https://markphamm.github.io/quickdbd-cli/ · **Live demo (200 tables):** https://markphamm.github.io/quickdbd-cli/demo/

Not affiliated with QuickDBD. It reads the same text syntax, so schemas move freely between the two.

## Features

- **Same syntax as QuickDBD:** tables, aliases, quoted names, all 9 relationship operators, `rel` lines, PK/FK/NULL/UNIQUE/INDEX/IDENTITY, `default=`, doc comments, `[settings]` and `[layout]` sections. Error messages are QuickDBD's own.
- **Interactive page:**
  - explorer sidebar: tables grouped by file or dbt folder, with search (`/`, Enter jumps to the best match)
  - table detail panel (dbt-docs style, for relationships): description, columns with type/keys/docs, and clickable **References** / **Referenced by** lists
  - minimap
  - click a table to focus on it and its neighbours
  - collapse tables: full / keys only / names only
  - hover a column to highlight its relationship
  - hover a dotted-underlined table or column to read its `#` doc comments
  - PNG/SVG export buttons, and **draw.io**: an editable diagrams.net file using draw.io's ER table shapes and crow's-foot arrows
  - **Path finder:** in a table's detail panel, type another table to see the shortest join path, highlighted on the canvas, with a ready-to-paste SQL `JOIN` (also `qdbd path erd/ --from payments --to customers`)
  - **Regions:** a shaded, labelled area per file or dbt folder (toolbar toggle). `--by-group` on `build` / `export` / `layout` arranges tables so each folder sits together
  - shareable links: the URL keeps the filter, selected table, collapse mode and zoom; **Link** copies it
- **Live editing:** `qdbd serve` reloads when you save, has a browser editor pane with autosave, and remembers where you drag tables.
- **Many files, one diagram:** point it at a folder and foreign keys can cross files.
- **Pip-only install:** no Graphviz, Node or browser needed. Layout uses [ELK](https://eclipse.dev/elk/), running in an embedded V8.
- **CI-friendly:** builds are deterministic, and errors are `file:line: error: …` with exit code 1.

## From a dbt project

```bash
dbt docs generate                                   # optional: adds real column types (catalog.json)
qdbd import dbt target/manifest.json -o erd/        # one .txt per folder (staging, marts, sources, ...)
qdbd build erd/ -o erd.html
```

- **Tables:** models, seeds and snapshots of your project, plus sources.
- **Relationships:** `relationships` tests (including dbt_utils `relationships_where`) and `foreign_key` constraints.
- **Primary keys:** `primary_key` constraints, or else a column with both `unique` and `not_null` tests.
- **Docs:** model and column descriptions become doc comments, shown as tooltips.
- **Options:**
  - `--select 'marts.*'` narrows by name, fqn or path (repeatable)
  - `--package all` includes installed packages
  - `--no-sources` drops sources
  - `-o schema.txt` writes a single file

Re-running the import overwrites the generated files. Table positions survive because they live in the layout file, keyed by table name.

## Selecting tables

Like dbt's `--select`, but it follows relationships instead of lineage. It works in the page's filter box and as `-s/--select` / `--exclude` on `build` and `export`.

| Selector | Tables |
|---|---|
| `orders` / `stg_*` | by name or alias (glob, case-insensitive) |
| `+orders` | `orders` and every table it references (any depth); `1+orders` limits to one hop |
| `orders+` | `orders` and every table that references it; `orders+2` limits to two hops |
| `+orders+1` | both directions |
| `group:marts` | a file or dbt folder (and its subfolders) |
| `file:core.txt` | a schema file (glob) |
| `col:customer_id` | tables with a matching column |
| `diff:modified` / `diff:added` / `diff:changed` | changed since `--diff-base` (like dbt `state:modified`) |
| `a b` / `a,b` / `!a` | union / intersection / exclude |

```bash
qdbd build erd/ -s 'group:marts' --exclude '*_tmp' -o marts.html
qdbd export erd/ -s '+orders+1' -o orders.png
```

## Schema diffs

```bash
qdbd diff old.txt new.txt                         # two versions
qdbd diff --base origin/main erd/                 # git ref vs working tree
qdbd diff --base origin/main erd/ --format markdown -o diff.md   # for a PR comment
qdbd build erd/ --diff-base origin/main -o erd.html              # colour what changed
```

`diff` reports tables added and removed, column changes (added, removed, type and flag changes) and relationships added and removed. `--format json` is available, and `--exit-code` exits 1 when anything changed.

With `--diff-base`, the page:
- marks new tables green and changed tables amber, with a bar on each changed column;
- shows a summary banner, and its **Show changes** link filters to the changes plus their neighbours;
- lists each table's changes in the detail panel.

The selector `diff:modified` (or `diff:added` / `diff:changed`) works like dbt's `state:modified`, e.g. `-s 'diff:modified+1'`.

## Commands

```bash
qdbd check  PATH... [--strict]                 # validate; "No errors found. Good job!"
qdbd build  PATH... -o diagram.html            # shareable interactive HTML
qdbd serve  PATH... [--port 8765]              # live editor + drag-to-arrange
qdbd export PATH... -o out.png [--focus Customer --depth 1]   # PNG, SVG or .drawio
qdbd layout PATH... [--reset]                  # (re)write the layout file
qdbd import dbt target/manifest.json -o erd/   # generate schema files from a dbt project
qdbd path PATH... --from A --to B              # shortest join path + SQL JOIN snippet
```

`PATH` is a `.txt` file or a folder. Every `*.txt` under a folder is read recursively.

### Table positions

The first build auto-arranges the tables. In `qdbd serve`, drag tables where you want them. Positions are saved to a sidecar file you can commit:

- `schema.txt` → `schema.layout.json`
- a folder → `<folder>/qdbd.layout.json`
- override either with `--layout FILE`

Once a layout exists, a new table is placed next to the tables it's related to, and nothing else moves. Run `qdbd layout PATH --reset` to re-arrange everything from scratch. A pasted schema's QuickDBD `[layout]` section is used for any table the sidecar doesn't cover.

`qdbd build` never writes the sidecar, so CI builds leave the working tree clean.

### Differences from QuickDBD

`qdbd` accepts a few things QuickDBD rejects, and prints a warning for each one:

- tab characters
- `decimal(10, 2)` (a space inside a type)
- an explicit `NOT NULL`
- indented table names
- `[layout]` entries for unknown tables

`qdbd check --strict` turns these warnings into errors, so a file that passes is guaranteed to paste into QuickDBD.

`default=` values keep their case, where QuickDBD lowercases them.

## CI

**GitHub Action:** checks the schema and builds the diagram. On pull requests it also posts one schema-diff comment, updated on every push, and highlights the changes in the diagram artifact.

```yaml
name: ERD
on: [pull_request, push]
jobs:
  erd:
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write }
    steps:
      - uses: actions/checkout@v4
      - uses: MarkPhamm/quickdbd-cli@v0.1.5
        with:
          path: erd/                 # schema file(s) or folder(s)
          output: site/index.html
```

| Input | Default | |
|---|---|---|
| `path` | (required) | schema files or folders |
| `output` | `erd/index.html` | HTML diagram path |
| `check` / `strict` | `true` / `false` | fail on errors / also on QuickDBD-compatibility warnings |
| `comment` | `true` | post the diff comment on PRs |
| `select` | | dbt-style selector for the diagram |
| `qdbd-version` | `latest` | PyPI version |

Outputs are `html`, `changed` and `diff-file`.

**Publishing:** to publish the diagram on GitHub Pages, add `actions/upload-pages-artifact` + `actions/deploy-pages` after it. See [`.github/workflows/erd.yml`](.github/workflows/erd.yml), which publishes this repo's demo.

**pre-commit:**

```yaml
repos:
  - repo: https://github.com/MarkPhamm/quickdbd-cli
    rev: v0.1.5
    hooks:
      - id: qdbd-check
        files: ^erd/.*\.txt$   # point at your schema files
```

**GitLab CI:**

```yaml
erd:
  image: python:3.12
  script:
    - pip install quickdbd-cli
    - qdbd check erd/
    - qdbd build erd/ -o public/index.html
  artifacts:
    paths: [public/index.html]
```

## Development

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
python scripts/gen_schema.py        # regenerate examples/synthetic (200 tables)
python scripts/gen_font_metrics.py  # regenerate font width table
```

Design notes: `docs/superpowers/specs/2026-10-17-qdbd-design.md`.

### Releasing

Put PyPI credentials in `.env` (gitignored):

```
TWINE_USERNAME=__token__
TWINE_PASSWORD=pypi-...
```

Bump `version` in `pyproject.toml` and `src/quickdbd_cli/__init__.py`, commit, then run `PATH="$PWD/.venv/bin:$PATH" scripts/release.sh`. It builds, uploads to PyPI, tags `vX.Y.Z` and creates the GitHub release.

## License

Apache-2.0. Bundled third-party files are listed in [NOTICE](NOTICE).
