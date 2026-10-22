# Changelog

## 0.1.1

- Fix: a schema file next to a folder that is its own project (has a layout file) was checked together with that project, giving "Table already defined" errors and an empty diagram. It's now checked on its own.

## 0.1.0

First release: highlighting, live diagnostics, outline, workspace symbols, go to definition, the diagram preview with cursor sync, and export / share commands. Needs qdbd 0.1.16+.
