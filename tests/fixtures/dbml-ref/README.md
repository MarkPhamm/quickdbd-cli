# DBML acceptance corpus

The snapshot test inputs of [@dbml/parse](https://github.com/holistics/dbml/tree/master/packages/dbml-parse)
10.3.1 (commit `34108bb9346df5f22d5224549c106ff47ca931c8`), the parser dbdiagram.io runs. Apache License 2.0
(see `LICENSE`).

Each `<stage>/<name>.dbml` has a `<name>.json` with the reference result reduced to what qdbd checks: the error
lines, or (interpreter stage, no errors) the tables, columns, refs and table groups. `tests/test_dbml.py` runs them.

Regenerate from a checkout of holistics/dbml with `python scripts/import_dbml_corpus.py PATH/TO/dbml`.
