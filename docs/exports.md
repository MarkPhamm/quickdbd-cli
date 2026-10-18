# Exports

Every export is drawn by the same renderer as the page, so images match what you see.

## From the page

The toolbar's **SVG**, **PNG** and **draw.io** buttons export the current view: the filter, the selected table and its neighbours (if one is selected), the collapse mode and regions.

## From the CLI

```bash
qdbd export erd/ -o erd.png                       # whole schema, PNG (2x)
qdbd export erd/ -o orders.svg --focus orders     # a table and its direct neighbours
qdbd export erd/ -o marts.drawio -s 'group:marts' # editable draw.io file
```

| Option | |
|---|---|
| `-o FILE` | `.png`, `.svg` or `.drawio` |
| `-s` / `--exclude` | [selectors](selectors.md); the selection gets a compact fresh layout |
| `--focus TABLE --depth N` | a table and everything within N relationship hops |
| `--mode full\|keys\|header` | collapse mode |
| `--regions` / `--by-group` | regions per file or dbt folder |
| `--scale 2` | PNG pixel scale |

PNG rendering uses [resvg](https://github.com/linebender/resvg) with the bundled Inter font, so output is identical on every machine and needs no browser.

## draw.io

`.drawio` files open in [draw.io / diagrams.net](https://app.diagrams.net) (desktop, web, VS Code and Confluence plugins) as **editable** diagrams:

- tables use draw.io's own Entity Relation table shapes, with a key column (`PK`, `FK`, `PK,FK`) and `name [flags] : type` rows;
- lines attach to the actual column rows and use draw.io's ER arrows (one, many, zero-or-one, zero-or-many), so they re-route when you move tables;
- regions become background rectangles.
