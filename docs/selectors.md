# 4.2 Selecting Tables

qdbd's selectors are modelled on dbt's `--select`, but they follow **relationships** instead of lineage. The same syntax works in the page's filter box and as `-s/--select` and `--exclude` on `build` and `export`.

## Syntax

| Selector | Tables |
|---|---|
| `orders` | by name or alias |
| `stg_*`, `*_dim`, `ord?rs` | glob, case-insensitive; `?` also matches a space (`Product?Catalog`) |
| `+orders` | `orders` and every table it references, at any depth |
| `1+orders` | … only one hop |
| `orders+` | `orders` and every table that references it |
| `orders+2` | … up to two hops |
| `+orders+1` | both directions |
| `group:marts` | a file or dbt folder (and its subfolders, e.g. `marts/finance`) |
| `file:core.txt` | a schema file, glob |
| `col:customer_id` | tables with a matching column |
| `tag:fact` | tables with a matching [tag](tags.md) (explicit, from the name, or from dbt) |
| `diff:modified` | changed since `--diff-base` (`diff:added`, `diff:changed`), like dbt's `state:modified` |

Combine them:

| Form | Meaning |
|---|---|
| `a b` | union: either |
| `a,b` | intersection: both, e.g. `col:customer_id,group:marts` |
| `!a` | exclude (in the page; on the CLI use `--exclude a`) |

"References" follows foreign keys from the table that holds them (the *many* side) to the table they point at.

## Examples

```bash
qdbd build erd/ -s 'group:marts' --exclude '*_tmp' -o marts.html
qdbd export erd/ -s '+orders+1' -o orders.png
qdbd build erd/ --diff-base origin/main -s 'diff:modified+1' -o changes.html
```

In the page, a filter shows "Showing N of M tables"; shareable links keep it.
