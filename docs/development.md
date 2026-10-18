# Local Development

```bash
git clone https://github.com/MarkPhamm/quickdbd-cli && cd quickdbd-cli
uv venv && uv pip install -e ".[dev,docs]"
.venv/bin/pytest
```

## Layout of the repo

| Path | |
|---|---|
| `src/quickdbd_cli/parser.py` | QuickDBD-compatible parser |
| `src/quickdbd_cli/assets/render.js` | the one renderer: SVG, draw.io, selectors, path finder (runs in the browser and, via embedded V8, in the CLI) |
| `src/quickdbd_cli/assets/viewer.js` | the interactive page |
| `src/quickdbd_cli/layout.py` | ELK layout, placement of new tables, layout files |
| `src/quickdbd_cli/dbt.py`, `diff.py`, `serve.py` | dbt import, diffs, live editor |
| `action.yml` | the GitHub Action |
| `docs/`, `mkdocs.yml` | this site |

## Docs

```bash
.venv/bin/mkdocs serve        # http://127.0.0.1:8000
```

The site deploys to GitHub Pages from `main`, with the live demos built into `/demo/`.

## Example data

```bash
python scripts/gen_schema.py         # regenerate examples/synthetic (200 tables)
python scripts/gen_font_metrics.py   # regenerate the font width table
```

## Releasing

Put PyPI credentials in `.env` (gitignored): `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=pypi-…`. Bump `version` in `pyproject.toml` and `src/quickdbd_cli/__init__.py`, commit, then:

```bash
PATH="$PWD/.venv/bin:$PATH" scripts/release.sh
```

It builds, uploads to PyPI, tags `vX.Y.Z` and creates the GitHub release.
