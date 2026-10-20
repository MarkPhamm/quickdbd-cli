Trimmed `manifest.json` / `catalog.json` from [OHDSI/dbt-synthea](https://github.com/OHDSI/dbt-synthea)
(Apache-2.0, see LICENSE) at commit `33fdbfa9b354f00def5ee6e45525cb2da80e0ddf`, keeping only the keys
`qdbd import dbt` reads. Seeds (Synthea data and the OMOP vocabulary subset) are not included.

Made with dbt-core 1.11.11 + dbt-duckdb 1.10.1, using the project's own seeds:

    dbt deps && dbt seed && dbt run && dbt docs generate
