# 5.2 Worked Example: jaffle_shop

This example takes dbt Labs' [jaffle_shop](https://github.com/dbt-labs/jaffle_shop_duckdb) from a dbt project to a reviewed, published ERD. It's small (8 tables), so every step fits on screen, but nothing changes at 200 tables.

| Step | You'll | Commands |
|---|---|---|
| [Step 1: Import from dbt](import.md) | Generate schema files from `manifest.json` | `dbt docs generate`, `qdbd import dbt` |
| [Step 2: Explore the model](explore.md) | Read tables, docs and relationships; find join paths | `qdbd serve`, `qdbd path` |
| [Step 3: Review a change](review.md) | See what a branch changes before merging | `qdbd diff`, `qdbd build --diff-base` |
| [Step 4: Automate in CI](ci.md) | Comment on PRs and publish the diagram | the GitHub Action |

<iframe class="demo" src="../demo/jaffle/" title="jaffle_shop ERD"></iframe>

*The jaffle_shop diagram, live. Click `orders`, try the filter `+orders`, or open it [full screen](../demo/jaffle/).*
