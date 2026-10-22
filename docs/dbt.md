# 5.1 dbt Import

```bash
qdbd import dbt target/manifest.json -o erd/
```

`manifest.json` (or the `target/` directory) is all qdbd needs. If `catalog.json` sits next to it (`dbt docs generate`), column types come from it automatically.

!!! tip "Run `dbt docs generate` first"
    `manifest.json` only knows the columns you've documented in YAML. `catalog.json`, written by `dbt docs generate`, lists every column in the warehouse with its type. Without it, undocumented models show up with no columns, and qdbd prints a hint saying how many.

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
| Tags | dbt `tags`, written as `# @dbt-tags:` comments; they colour the headers ([3.5 Tags and Colours](tags.md)) |

## Options

| Option | |
|---|---|
| `-o schema.txt` | one file |
| `-o erd/` | one file per dbt folder (`staging.txt`, `marts.txt`, `sources.txt`, …); stale generated files are removed, your own files are kept |
| `--catalog FILE` | catalog location if it isn't next to the manifest |
| `--package NAME` | include an installed package (repeatable; `all` for every package). Default: your project only |
| `--select GLOB` | only nodes whose name, fqn (`proj.marts.orders`) or path matches (repeatable) |
| `--no-sources` | leave sources out |
| `--infer-fks` | also guess relationships from column names (below) |
| `--check` | don't write; exit 1 if the files at `-o` are out of date (CI) |

The generated text is compiled before anything is written; if qdbd can't read its own output, it stops instead of writing a broken schema.

## Guessing relationships: `--infer-fks`

Most dbt projects declare few `relationships` tests, so a plain import can show 200 tables with hardly any lines. `--infer-fks` adds the obvious ones from column names:

```bash
qdbd import dbt target/ -o erd/ --infer-fks
```

```text
inferred: stg_orders.customer_id -> stg_customers.customer_id
inferred: stg_payments.order_id -> stg_orders.order_id
inferred: raw_payments.order_id -> raw_orders.id
Wrote erd/ (3 files): 8 tables, 4 relationships (3 inferred)
```

How a column is matched:

1. Its name ends in `_id`, `_key`, `_sk`, `Id` or `Key`; the rest is the entity (`customer_id` → `customer`).
2. Candidate parents are tables named after the entity, after removing a dbt layer prefix (`stg_`, `int_`, `dim_`, `fct_`, `raw_`, …) and any source qualifier (`stg_shop__customers` → `customers`), in singular or plural (`customer`, `customers`, `categories`).
3. The parent needs a matching key: a column with the same name (`customer_id`, `customerId`) or `id`.
4. If several tables qualify, qdbd picks `dim_` parents for `fct_` children, else the same layer as the child (`stg_` → `stg_`), then the same folder, then a declared primary key. If that still leaves a tie, the column is **skipped** and reported, never guessed.

Declared relationships always win, and a table's own single primary key is never turned into a foreign key. Inferred columns say so in their description (and tooltip), so readers can tell them apart.

## Keeping committed files current: `--check`

If you commit the generated files (recommended: pull requests can then diff them), check in CI that they match the project:

```bash
qdbd import dbt target/ -o erd/ --check
```

It writes nothing. It exits 0 when everything matches, or prints each stale, missing or no-longer-generated file and exits 1, like a generated-code check.

## Refreshing

Re-run the import whenever models change. Generated files say so in their header and are overwritten. Positions are in `qdbd.layout.json`, keyed by table name, so your arrangement survives. New models are placed next to their related tables.

!!! note "Relationships come from your tests"
    dbt has no foreign keys of its own. qdbd draws the relationships your project declares through `relationships` tests or `foreign_key` constraints, plus, with `--infer-fks`, the ones it can read from column names. Adding `relationships` tests both documents and tests your joins.
