# 9. Development

```bash
git clone https://github.com/MarkPhamm/quickdbd-cli && cd quickdbd-cli
uv venv && uv pip install -e ".[dev,docs]"
.venv/bin/pytest
```

## 9.1 Layout of the repo { #layout-of-the-repo }

| Path | |
|---|---|
| `src/quickdbd_cli/parser.py` | QuickDBD-compatible parser |
| `src/quickdbd_cli/assets/render.js` | the one renderer: SVG, draw.io, selectors, path finder (runs in the browser and, via embedded V8, in the CLI) |
| `src/quickdbd_cli/assets/viewer.js` | the interactive page |
| `src/quickdbd_cli/layout.py` | ELK layout, placement of new tables, layout files |
| `src/quickdbd_cli/dbt.py`, `diff.py`, `serve.py` | dbt import, diffs, live editor |
| `src/quickdbd_cli/mcp.py`, `agent.py`, `targets.py` | `qdbd mcp`: the protocol, the agent tools, finding schema projects in a folder |
| `action.yml` | the GitHub Action |
| `docs/`, `mkdocs.yml` | this site |

## 9.2 Docs { #docs }

```bash
.venv/bin/mkdocs serve        # http://127.0.0.1:8000
```

The site deploys to GitHub Pages from `main`, with the demo gallery built into `/demo/`.

## Demo gallery

`gallery/demos.toml` lists every demo: its source (a QuickDBD path or a dbt manifest folder), build flags, and the viewer URL hash its card opens. To add one:

1. Add a `[[demo]]` entry (the file's header comment lists the keys).
2. Run `python scripts/gen_thumbnails.py <id>` to make its card image in `docs/assets/img/gallery/` (needs Playwright; uses the system Chrome).
3. Preview with `python scripts/build_gallery.py --out /tmp/site/demo` and open `/tmp/site/demo/index.html`.

Demos marked `featured = true` (four of them) fill the table in the README: after changing one, run `python scripts/build_gallery.py --readme`. The `[hero]` entry picks the screenshot at the top of the README (`python scripts/gen_thumbnails.py hero`).

`tests/test_gallery.py` checks the catalog, that every demo has a thumbnail, that the README table is in sync, and that the build is deterministic.

## 9.3 Example data { #example-data }

```bash
python scripts/gen_schema.py         # regenerate examples/synthetic (200 tables)
python scripts/gen_font_metrics.py   # regenerate the font width table
```

## 9.4 Releasing { #releasing }

Put PyPI credentials in `.env` (gitignored): `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=pypi-…`. Bump `version` in `pyproject.toml` and `src/quickdbd_cli/__init__.py`. Bump the version pins in the docs too (`grep -rn '@v0\.\|rev: v0\.' README.md docs`). Commit, then:

```bash
PATH="$PWD/.venv/bin:$PATH" scripts/release.sh
```

It builds, uploads to PyPI, tags `vX.Y.Z` and creates the GitHub release.

The VS Code extension has its own version, in `vscode/package.json` and `vscode/CHANGELOG.md`. Bump it only when the extension changes. `release.sh` attaches the `.vsix` to the GitHub release and publishes to Open VSX when `OVSX_PAT` is in `.env`. The VS Code Marketplace upload is manual, at marketplace.visualstudio.com/manage.
