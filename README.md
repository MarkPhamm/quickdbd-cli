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

Not affiliated with QuickDBD. It reads the same text syntax, so schemas move freely between the two.

## Features

- **Same syntax as QuickDBD:** tables, aliases, quoted names, all 9 relationship operators, `rel` lines, PK/FK/NULL/UNIQUE/INDEX/IDENTITY, `default=`, doc comments, `[settings]` and `[layout]` sections. Error messages are QuickDBD's own.
- **Interactive page:**
  - search and jump to a table (`/`)
  - minimap
  - click a table to focus on it and its neighbours
  - collapse tables: full / keys only / names only
  - hover a column to highlight its relationship
  - PNG/SVG export buttons
- **Live editing:** `qdbd serve` reloads when you save, has a browser editor pane with autosave, and remembers where you drag tables.
- **Many files, one diagram:** point it at a folder and foreign keys can cross files.
- **Pip-only install:** no Graphviz, Node or browser needed. Layout uses [ELK](https://eclipse.dev/elk/), running in an embedded V8.
- **CI-friendly:** builds are deterministic, and errors are `file:line: error: …` with exit code 1.

## Commands

```bash
qdbd check  PATH... [--strict]                 # validate; "No errors found. Good job!"
qdbd build  PATH... -o diagram.html            # shareable interactive HTML (positions locked)
qdbd serve  PATH... [--port 8765]              # live editor + drag-to-arrange
qdbd export PATH... -o out.png [--focus Customer --depth 1]   # PNG or SVG image
qdbd layout PATH... [--reset]                  # (re)write the layout file
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

**pre-commit:**

```yaml
repos:
  - repo: https://github.com/MarkPhamm/quickdbd-cli
    rev: v0.1.0
    hooks:
      - id: qdbd-check
        files: ^schema/.*\.txt$   # point at your schema files
```

**GitHub Actions:**

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install quickdbd-cli
- run: qdbd check schema/
- run: qdbd build schema/ -o site/schema.html
- uses: actions/upload-artifact@v4
  with: { name: schema-diagram, path: site/schema.html }
```

**GitLab CI:**

```yaml
erd:
  image: python:3.12
  script:
    - pip install quickdbd-cli
    - qdbd check schema/
    - qdbd build schema/ -o public/schema.html
  artifacts:
    paths: [public/schema.html]
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
