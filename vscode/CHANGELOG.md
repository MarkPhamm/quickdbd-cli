# Changelog

## 0.3.1

- Fix: the sidebar listed schema files inside hidden folders, such as an editor's local-history copies or a `.vscode-test` sandbox, as broken schemas. Hidden folders are skipped now, as dependency and build folders already were.

## 0.3.0

- **The QuickDBD sidebar**: an Activity Bar icon opens **Schemas**, every schema in the workspace down to its tables and columns (types and keys with qdbd 0.1.18+), and **Actions**, every command one click away, including **Export…** and the new **New Schema File…**. With no qdbd or no schema yet, it shows the install or create buttons instead.
- Commands work without an open editor: from a sidebar row, the current schema, or a picker.

## 0.2.0

Everything works without a terminal:

- **Install qdbd** from the extension: when the CLI is missing or too old, one click installs it into a Python environment of the extension's own (Python 3.11+ or uv needed). **QuickDBD: Install or Update qdbd** does it any time.
- **Share as a Gist Link** signs in with VS Code's GitHub account instead of the gh CLI. It updates the same gist as before, so existing links keep working.
- New: **Compare with Git Ref…** opens the diagram coloured by what changed since a branch, tag or commit, and updates as you save.
- New: **Import dbt Project…** turns a dbt `target/manifest.json` into schema files and opens their diagram.
- New: **Export HTML Page** writes the interactive diagram as one file.

Needs qdbd 0.1.17+.

## 0.1.1

- Fix: a schema file next to a folder that is its own project (has a layout file) was checked together with that project, giving "Table already defined" errors and an empty diagram. It's now checked on its own.

## 0.1.0

First release: highlighting, live diagnostics, outline, workspace symbols, go to definition, the diagram preview with cursor sync, and export / share commands. Needs qdbd 0.1.16+.
