# 3.4 Table Positions

## Auto-layout

The first time qdbd sees a schema, it arranges the tables automatically with the [Eclipse Layout Kernel](https://eclipse.dev/elk/)'s stress layout, followed by overlap removal. Related tables end up close together and nothing overlaps. Tall results are turned 90° to fit screens.

## The layout file

Tables can be dragged in any diagram. In `qdbd serve`, the positions are saved to a sidecar file:

| Input | Layout file |
|---|---|
| `schema.txt` | `schema.layout.json` |
| a folder | `<folder>/qdbd.layout.json` |
| anything | `--layout FILE` overrides |

It's small, sorted JSON keyed by table name. Commit it with the schema so everyone sees the same arrangement. `qdbd build` reads it but never writes it, so CI leaves your working tree clean.

## New tables

When a table appears that isn't in the layout file, qdbd places it in free space **next to the tables it's related to**. Nothing you've arranged moves. In `serve`, the new position is saved straight away.

A pasted QuickDBD schema's `[layout]` section is used for tables the layout file doesn't cover.

## Starting over

```bash
qdbd layout erd/ --reset        # fresh auto-layout for everything, saved to the layout file
qdbd layout erd/ --by-group     # fresh layout keeping each file / dbt folder together
```

`--by-group` lays out each group on its own and packs the groups as blocks, so [regions](reading-the-diagram.md#regions) never overlap. It also works on `build` and `export` without touching the layout file.
