# qdbd: QuickDBD diagrams from the command line

`qdbd` turns [QuickDBD](https://www.quickdatabasediagrams.com)-syntax `.txt` schemas, or a dbt project, into **interactive ER diagrams** with **no table limit**. The diagrams stay readable at 200+ tables.

<p>
  <a href="https://markphamm.github.io/quickdbd-cli/demo/"><b>▶ Live demo (200 tables)</b></a> ·
  <a href="https://markphamm.github.io/quickdbd-cli/demo/jaffle/"><b>▶ dbt demo (jaffle_shop)</b></a> ·
  <a href="https://markphamm.github.io/quickdbd-cli/"><b>📖 Docs</b></a> ·
  <a href="https://pypi.org/project/quickdbd-cli/">PyPI</a>
</p>

[![The 200-table demo](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/overview.png)](https://markphamm.github.io/quickdbd-cli/demo/)

Not affiliated with QuickDBD. It reads the same text syntax, so schemas can be copied back and forth between the two.

---

**Contents**

1. [Install](#1-install)
2. [Quick start: your first diagram in 5 minutes](#2-quick-start-your-first-diagram-in-5-minutes)
3. [Working with schema files](#3-working-with-schema-files)
4. [Exploring a diagram](#4-exploring-a-diagram)
5. [dbt projects](#5-dbt-projects)
6. [Reviewing schema changes](#6-reviewing-schema-changes)
7. [CI and automation](#7-ci-and-automation)
8. [Command reference](#8-command-reference)
9. [Development](#9-development)

---

## 1. Install

```bash
pipx install quickdbd-cli      # or: pip install quickdbd-cli / uv tool install quickdbd-cli
qdbd --version
```

- **Requirements:** Python 3.11+. Nothing else: no Graphviz, Node or browser. Layout uses [ELK](https://eclipse.dev/elk/) running in an embedded JavaScript engine.
- **Try it without installing:** prefix any command with `uvx --from quickdbd-cli`, e.g. `uvx --from quickdbd-cli qdbd build schema.txt -o schema.html`.
- **`qdbd: command not found`?** `pip install` put the script in a directory that isn't on your `PATH`. Use `pipx`, or run `python -m pip show -f quickdbd-cli` to find it.

## 2. Quick start: your first diagram in 5 minutes

### 2.1 Write (or paste) a schema

Save this as `schema.txt`. If you already have a schema in QuickDBD, copy it from the editor and paste it in unchanged.

```text
Customer
-
CustomerId PK int
Name string
Email string UNIQUE

Order as o
----
OrderId PK int
CustomerId int FK >- Customer.CustomerId
OrderDate datetime
Total decimal(10,2)
```

A table is a name, a line of dashes, then one column per line. `FK >- Customer.CustomerId` means *many orders → one customer*. See the [syntax cheat sheet](#31-syntax-cheat-sheet).

### 2.2 Check it

```bash
qdbd check schema.txt
```

```text
No errors found. Good job!
```

Errors print as `schema.txt:12: error: …` (QuickDBD's own messages) and exit with code 1.

### 2.3 Edit it live

```bash
qdbd serve schema.txt
```

A browser tab opens with the diagram and an editor pane.

- **Edit** in the pane (it autosaves after 1 s) or in your own editor. The diagram reloads on save.
- **Drag tables** to arrange them. Positions are saved to `schema.layout.json`; commit it next to the schema.
- **Stop** with `Ctrl+C`.

### 2.4 Build a page to share

```bash
qdbd build schema.txt -o schema.html
```

`schema.html` is a single self-contained file. Open it locally, email it, attach it to a ticket, or publish it on GitHub Pages ([7.1](#71-github-action)). To send a link instead of the file, see [4.4](#44-share-a-link).

### 2.5 Export an image

```bash
qdbd export schema.txt -o schema.png                       # whole diagram (.png, .svg or .drawio)
qdbd export schema.txt --focus Order --depth 1 -o order.svg   # one table and its neighbours
```

`.drawio` files open in [diagrams.net](https://app.diagrams.net) as editable ER shapes.

## 3. Working with schema files

### 3.1 Syntax cheat sheet

```text
# A comment above a table or column becomes its tooltip
"Sales Order" as so          # quote names with spaces or dots; "as" adds an alias
--------------
Id PK int IDENTITY
CustomerId int FK >- Customer.Id
Status varchar(20) default=new INDEX
Notes text NULL              # columns are NOT NULL unless marked NULL
```

| Column keyword | Meaning |
|---|---|
| `PK` | primary key (several `PK` columns make a composite key) |
| `FK >- Table.Column` | foreign key with a relationship |
| `NULL` / `NULLABLE` | nullable |
| `UNIQUE`, `INDEX` | unique key, index |
| `IDENTITY` / `AUTOINCREMENT` | auto-generated |
| `default=value` | default value |

| Relationship | Meaning (left → right) |
|---|---|
| `-` | one to one |
| `-<` / `>-` | one to many / many to one |
| `>-<` | many to many |
| `-0` / `0-` / `0-0` | involving zero-or-one |
| `-0<` / `>0-` | involving zero-or-many |

Full reference: [Schema Syntax](https://markphamm.github.io/quickdbd-cli/syntax/).

### 3.2 One folder, many files

Big schemas are easier to manage split into files. Point any command at a folder and every `*.txt` under it (recursively) becomes **one** diagram:

```text
schema/
├── sales.txt        # Order, OrderLine, Invoice …
├── customers.txt    # Customer, Address …
└── products.txt
```

```bash
qdbd build schema/ -o schema.html
```

- Foreign keys can point at tables in other files.
- Each file becomes a group in the sidebar and can be shaded as a **region**.
- `--by-group` arranges the tables so each file's tables sit together.

### 3.3 Table positions

| Situation | What happens |
|---|---|
| First build | Tables are auto-arranged by their relationships |
| You drag tables in `qdbd serve` | Positions are saved to the layout file |
| You add a new table later | It's placed next to the tables it's related to. Nothing else moves |
| Schema pasted from QuickDBD with a `[layout]` section | Those positions are used for tables the layout file doesn't cover |
| You want a fresh arrangement | `qdbd layout PATH --reset` |

Where the layout file goes:

- `schema.txt` → `schema.layout.json`
- a folder → `<folder>/qdbd.layout.json`
- anywhere else: `--layout FILE`

`qdbd build` never writes the layout file, so CI builds leave your working tree clean. More: [Table Positions](https://markphamm.github.io/quickdbd-cli/layout/).

### 3.4 Tags and colours

Give tables a role and a header colour. Tags are comments, so the file still pastes into QuickDBD.

```text
# @color gold #b8860b      # optional: pick a tag's colour

# @tag: gold, pii
customers
-
customer_id PK int

dim_date                   # tagged "dim" automatically from its name
-
date_key PK int
```

A table's tags come from the first source that has any:

1. an explicit `# @tag:` comment;
2. its name: `dim_*` → dim, `fct_*` / `fact_*` → fact, `stg_*` → staging, `int_*` → intermediate, `raw_*` / `src_*` → raw;
3. dbt tags, written as `# @dbt-tags:` by `qdbd import dbt`.

The header takes the colour of the first tag. In the page, a chip per tag under the filter box shows only that tag, and the selector `tag:fact` works everywhere. More: [Tags and Colours](https://markphamm.github.io/quickdbd-cli/tags/).

### 3.5 Differences from QuickDBD

`qdbd` accepts a few things QuickDBD rejects, and prints a warning for each:

- tab characters
- a space inside a type: `decimal(10, 2)`
- an explicit `NOT NULL`
- indented table names
- `[layout]` entries for tables that don't exist

`qdbd check --strict` turns these warnings into errors, so a file that passes will paste into QuickDBD cleanly. Also, `default=` values keep their case, where QuickDBD lowercases them.

## 4. Exploring a diagram

Every page from `build` or `serve` works the same way. A full tour is in [Reading the Diagram](https://markphamm.github.io/quickdbd-cli/reading-the-diagram/).

### 4.1 Page tour

![Table details panel](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/details.png)

| Part | What you can do |
|---|---|
| **Explorer** (left) | Tables grouped by file. Press `/` to search; Enter jumps to the best match |
| **Canvas** | Drag tables, drag empty space to pan, scroll to zoom. Hover a column to highlight its relationships |
| **Details panel** (right) | Click a table: columns, doc comments, *References* / *Referenced by*, path finder |
| **Toolbar** (top right) | Collapse tables (Full / Keys / Names), Regions, **Link**, SVG / PNG / draw.io download, zoom |
| **Minimap** (bottom right) | Click or drag to move around |

**Link** copies a URL to exactly what you're looking at: the filter, selected table, path, collapse mode and zoom. Send it to a teammate.

### 4.2 Filter with selectors

The explorer's filter box takes dbt-style selectors that follow **relationships** (not lineage). The same selectors work as `-s/--select` and `--exclude` on `build` and `export`.

| Selector | Tables |
|---|---|
| `orders`, `stg_*` | by name or alias (glob, case-insensitive) |
| `+orders` / `orders+` | `orders` and what it references / what references it |
| `+orders+1` | one hop in both directions |
| `group:marts`, `file:core.txt` | a folder or a file |
| `col:customer_id` | tables with a matching column |
| `tag:fact` | tables with a matching tag ([3.4](#34-tags-and-colours)) |
| `a b` / `a,b` / `!a` | union / intersection / exclude |

```bash
qdbd build erd/ -s 'group:marts' --exclude '*_tmp' -o marts.html
qdbd export erd/ -s '+orders+1' -o orders.png
```

![Filter +Order+1](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/filter.png)

More: [Selecting Tables](https://markphamm.github.io/quickdbd-cli/selectors/).

### 4.3 Find how two tables join

In a table's details panel, type another table's name. The shortest join path is highlighted on the canvas, with a ready-to-paste SQL `JOIN`. From the terminal:

```bash
qdbd path schema/ --from Invoice --to Campaign
```

![Path from Invoice to Campaign](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/path.png)

### 4.4 Share a link

`qdbd serve`'s address only works on your machine. To send someone a **link**:

```bash
qdbd share schema.txt          # needs the GitHub CLI: brew install gh && gh auth login
```

```text
Shared 12 tables (secret gist https://gist.github.com/you/1a2b3c…)
Link: https://gistpreview.github.io/?1a2b3c…
```

- The link opens the full interactive page. Running `qdbd share` again updates the same link.
- Gists are secret (link-only) by default; `--public` lists it.
- For a **live** view while you edit, run `qdbd serve schema.txt --read-only` (no editor, nothing written to disk) behind a tunnel such as `cloudflared tunnel --url http://127.0.0.1:8765`. Never tunnel a plain `qdbd serve`: viewers could edit your files.

More: [Sharing a Link](https://markphamm.github.io/quickdbd-cli/sharing/).

## 5. dbt projects

### 5.1 Generate the schema from dbt

```bash
cd your-dbt-project
dbt docs generate                                # writes target/manifest.json + catalog.json
qdbd import dbt target/ -o erd/ --infer-fks      # one .txt per dbt folder
qdbd build erd/ --by-group -o erd.html           # open erd.html
```

`dbt docs generate` is what supplies column names and types for models without documented columns. Without it, many tables show up with no columns and `qdbd` prints a hint.

See it on a real project: the [jaffle_shop demo](https://markphamm.github.io/quickdbd-cli/demo/jaffle/) and the [step-by-step walkthrough](https://markphamm.github.io/quickdbd-cli/example/).

### 5.2 What gets imported

| In the diagram | Comes from |
|---|---|
| Tables | your project's models, seeds and snapshots, plus sources |
| Primary keys | `primary_key` constraints, or a column with both `unique` and `not_null` tests |
| Relationships | `relationships` tests (incl. dbt_utils `relationships_where`) and `foreign_key` constraints |
| Column types | `catalog.json` |
| Tooltips | model and column descriptions |
| Header colours | dbt `tags` (unless the name or an explicit `# @tag` says otherwise) |

Useful options: `--select 'marts.*'` (repeatable), `--no-sources`, `--package all`, `-o schema.txt` for a single file.

### 5.3 Infer missing relationships

Most dbt projects don't declare every foreign key. `--infer-fks` links columns like `customer_id` to the table they name (`dim_customers`, `stg_shop__customers`, …) when no relationship is declared. Ambiguous matches are skipped, never guessed.

### 5.4 Keep it in sync

Re-run the import whenever models change. It overwrites the generated `.txt` files. Your dragged positions survive, because the layout file is keyed by table name. In CI, `--check` fails if the committed files are out of date ([7.2](#72-dbt-projects-in-ci)).

More: [dbt Import](https://markphamm.github.io/quickdbd-cli/dbt/).

## 6. Reviewing schema changes

### 6.1 See what changed

```bash
qdbd diff old.txt new.txt                       # two versions
qdbd diff --base origin/main erd/               # a git branch vs your working tree
qdbd diff --base origin/main erd/ --format markdown -o diff.md   # for a PR comment
```

It reports tables, columns (added, removed, type and flag changes) and relationships added or removed. `--format json` is also available, and `--exit-code` exits 1 when anything changed.

### 6.2 Highlight changes in the diagram

```bash
qdbd build erd/ --diff-base origin/main -o erd.html
```

New tables are green and changed tables amber, with a bar on each changed column. A banner summarises the changes, and **Show changes** filters to them plus their neighbours. The selector `diff:modified+1` does the same from the CLI.

![Diff view](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/diff.png)

More: [Schema Diffs](https://markphamm.github.io/quickdbd-cli/diffs/).

## 7. CI and automation

### 7.1 GitHub Action

Checks the schema and builds the diagram. On pull requests it also posts **one** schema-diff comment (updated on every push) and uploads the diagram with the changes highlighted.

```yaml
# .github/workflows/erd.yml
name: ERD
on: [pull_request, push]
jobs:
  erd:
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write }
    steps:
      - uses: actions/checkout@v4
      - uses: MarkPhamm/quickdbd-cli@v0.1.8
        with:
          path: erd/                  # schema file(s) or folder(s)
          output: site/index.html
```

| Input | Default | |
|---|---|---|
| `path` | `erd/` | schema files or folders |
| `output` | `erd/index.html` | where to write the HTML |
| `check` / `strict` | `true` / `false` | fail on errors / also on QuickDBD-compatibility warnings |
| `comment` | `true` | post the diff comment on PRs |
| `select` | | selector for the diagram, e.g. `group:marts` |
| `qdbd-version` | `latest` | PyPI version |

Outputs: `html`, `changed`, `diff-file`. To publish the diagram on GitHub Pages, add `actions/upload-pages-artifact` + `actions/deploy-pages`; this repo's [`erd.yml`](https://github.com/MarkPhamm/quickdbd-cli/blob/main/.github/workflows/erd.yml) does that for the live demo. All inputs: [GitHub Action](https://markphamm.github.io/quickdbd-cli/github-action/).

### 7.2 dbt projects in CI

Run your dbt setup first, then let the action generate the schema:

```yaml
      # … dbt deps && dbt build && dbt docs generate
      - uses: MarkPhamm/quickdbd-cli@v0.1.8
        with:
          dbt-manifest: target/
          dbt-args: --infer-fks
          path: erd/
          output: site/index.html
```

Commit `erd/` so pull requests can be compared with `main`. Set `dbt-check: true` to fail the job when the committed files are out of date instead of regenerating them. Walkthrough: [Automate in CI](https://markphamm.github.io/quickdbd-cli/example/ci/).

### 7.3 pre-commit

```yaml
repos:
  - repo: https://github.com/MarkPhamm/quickdbd-cli
    rev: v0.1.8
    hooks:
      - id: qdbd-check
        files: ^erd/.*\.txt$
```

### 7.4 GitLab CI (or any CI)

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

Builds are deterministic (no timestamps or randomness), so the output only changes when the schema does.

## 8. Command reference

```bash
qdbd check  PATH... [--strict]                      # validate
qdbd serve  PATH... [--port 8765] [--read-only]     # live editor + drag to arrange
qdbd build  PATH... -o diagram.html                 # interactive HTML
qdbd share  PATH... [--public]                      # publish as a gist, print a link
qdbd export PATH... -o out.png|.svg|.drawio [--focus T --depth 1]
qdbd layout PATH... [--reset]                       # (re)write the layout file
qdbd path   PATH... --from A --to B                 # shortest join path + SQL JOIN
qdbd diff   OLD NEW | --base REF PATH...            # schema changes
qdbd import dbt target/ -o erd/ [--infer-fks]       # schema files from dbt
```

`PATH` is a `.txt` file or a folder (read recursively). Run `qdbd COMMAND --help` for every option, or see [The qdbd CLI](https://markphamm.github.io/quickdbd-cli/cli/).

## 9. Development

```bash
uv venv && uv pip install -e ".[dev,docs]"
.venv/bin/pytest                                      # full suite
.venv/bin/ruff check src tests scripts && .venv/bin/ruff format src tests scripts
.venv/bin/mkdocs serve                                # docs site at localhost:8000
.venv/bin/qdbd serve examples/synthetic               # 200-table playground
```

More: [Local Development](https://markphamm.github.io/quickdbd-cli/development/). The design notes are in [`docs/superpowers/specs/`](docs/superpowers/specs/2026-10-17-qdbd-design.md).

### 9.1 Releasing

1. Put PyPI credentials in `.env` (gitignored): `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=pypi-…`.
2. Bump `version` in `pyproject.toml` and `src/quickdbd_cli/__init__.py`, then merge.
3. Run `PATH="$PWD/.venv/bin:$PATH" scripts/release.sh`. It builds, uploads to PyPI, tags `vX.Y.Z` and creates the GitHub release.

## License

Apache-2.0. Bundled third-party files (ELK, Inter) are listed in [NOTICE](https://github.com/MarkPhamm/quickdbd-cli/blob/main/NOTICE).
