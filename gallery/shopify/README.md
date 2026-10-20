Trimmed `manifest.json` / `catalog.json` from Fivetran's [dbt_shopify](https://github.com/fivetran/dbt_shopify)
package (Apache-2.0, see LICENSE) at commit `a455111f911c91be545dd1be2a018e3b53fecca1`, keeping only the
`shopify` package's nodes and the keys `qdbd import dbt` reads.

Made with dbt-core 1.11.11 + dbt-duckdb 1.10.1 from the package's `integration_tests/` project:

    dbt deps && dbt seed && dbt run && dbt docs generate

The gallery imports the REST API models only (`--package shopify --select 'shopify.rest.*'`) with
`--infer-fks`, since the package declares no relationship tests.
