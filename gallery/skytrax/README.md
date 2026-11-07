The hand-written ERD (`erd/`) and the dbt yml it links to, from
[MarkPhamm/qdbd-dbt-demo](https://github.com/MarkPhamm/qdbd-dbt-demo) (Apache-2.0, see LICENSE) at commit
`dddef9fd6750e1605a8ac33404ac0cc1a401dbc4`. Only what qdbd reads is kept: `dbt_project.yml`, the mart folders'
`*.yml` and `models/docs.md`. SQL, data, macros and CI are in the source repo.

`erd/conformed.txt` holds the `# @dbt: ..` line, so the yml descriptions, `pii` tags and `data_type`s show up in the
diagram with no `manifest.json`.
