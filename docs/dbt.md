# dbt Import

```bash
qdbd import dbt target/manifest.json -o erd/
```

`manifest.json` (or the `target/` directory) is all qdbd needs. If `catalog.json` sits next to it (`dbt docs generate`), column types come from it automatically.

## What gets imported

| In the schema | From dbt |
|---|---|
| Tables | models, seeds and snapshots of your project, plus sources (`"source_name.table"`) |
| Columns | documented columns, catalog columns, and columns used by tests |
| Types | `catalog.json`, else `data_type`. Multi-word types are shortened (`character varying(255)` → `varchar(255)`) |
| Primary keys | `primary_key` constraints, else the first column with both `unique` and `not_null` tests |
| UNIQUE | `unique` tests and constraints |
| Relationships | `relationships` tests (incl. dbt_utils `relationships_where`) and `foreign_key` constraints (`to` / `to_columns`, or `expression`) |
| Cardinality | many-to-one (`>-`), or one-to-one (`-`) when the child column is unique |
| Documentation | model and column descriptions, shown as tooltips |

## Options

| Option | |
|---|---|
| `-o schema.txt` | one file |
| `-o erd/` | one file per dbt folder (`staging.txt`, `marts.txt`, `sources.txt`, …); stale generated files are removed, your own files are kept |
| `--catalog FILE` | catalog location if it isn't next to the manifest |
| `--package NAME` | include an installed package (repeatable; `all` for every package). Default: your project only |
| `--select GLOB` | only nodes whose name, fqn (`proj.marts.orders`) or path matches (repeatable) |
| `--no-sources` | leave sources out |

The generated text is compiled before anything is written; if qdbd can't read its own output, it stops instead of writing a broken schema.

## Refreshing

Re-run the import whenever models change. Generated files say so in their header and are overwritten. Positions are in `qdbd.layout.json`, keyed by table name, so your arrangement survives. New models are placed next to their related tables.

!!! note "Relationships come from your tests"
    dbt has no foreign keys of its own. qdbd draws the relationships your project declares through `relationships` tests or `foreign_key` constraints. If the import reports few relationships, adding those tests both documents and tests your joins.
