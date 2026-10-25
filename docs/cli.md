# 8. CLI Reference

Every command except [`mcp`](#mcp) takes one or more `PATH`s: a `.txt` or `.dbml` file, or a folder (every `*.txt` and `*.dbml` under it, recursively). QuickDBD and [DBML](dbml.md) files can be mixed. `qdbd <command> --help` shows all options.

## 8.1 check { #check }

```bash
qdbd check PATH... [--strict] [--format text|github|json] [--symbols] [--stdin-file FILE]
```

Validates the schema. Prints `No errors found. Good job!`, or `file:line: error: message` lines and exits 1. `--strict` also fails on [QuickDBD-compatibility warnings](syntax.md#where-qdbd-is-more-forgiving).

`--format` changes the output:

- `github` also prints [GitHub Actions annotations](https://docs.github.com/en/actions/reference/workflow-commands-for-github-actions#setting-an-error-message), so each problem shows on its line in the pull request's *Files changed* tab. Under `--strict`, warnings are annotated as errors. The [GitHub Action](github-action.md) turns this on for you.
- `json` prints one report to stdout, for editors, hooks and scripts:

```json
{
  "ok": false,
  "errors": 1,
  "warnings": 0,
  "diagnostics": [
    {"path": "schema/orders.txt", "line": 3, "severity": "error", "message": "Unrecognized keyword 'foo'"}
  ]
}
```

Paths are relative to the current directory. The exit code is the same in every format.

Two options are there for editors, and the [VS Code extension](vscode.md) uses both:

- `--symbols` (with `--format json`) adds `tables` (name, aliases, file, first and last line, columns with their lines) and `rels` (file, line and both ends) to the report.
- `--stdin-file FILE` reads that schema file's text from stdin instead of disk, so an unsaved buffer gets checked along with the other files on disk. `FILE` has to be one of the files being checked.

## 8.2 build { #build }

```bash
qdbd build PATH... -o diagram.html [-s SELECTOR] [--exclude SELECTOR] [--diff-base REF] [--by-group] [--layout FILE] [--strict]
```

Writes one self-contained HTML page. Builds are deterministic (same input, same bytes), and the layout file is read but never written.

## 8.3 serve { #serve }

```bash
qdbd serve PATH... [--port 8765] [--layout FILE] [--no-open] [--read-only | --embed] [--diff-base REF]
```

Local live editor on `127.0.0.1`: reloads when files change, browser editor pane with autosave, drag tables to save positions. Ctrl+C stops it. The [VS Code extension](vscode.md#what-you-get)'s **Open in Browser** runs this, on any free port.

The default port is 8765. If it's busy (for example, a second `qdbd serve` is running), the next free port is used and printed. An explicit `--port` that's busy is an error.

`--read-only` serves a live view with no editor that never writes to disk, safe to put behind a tunnel ([4.4 Sharing a Link](sharing.md#live-read-only-link)).

`--embed` is the page behind the [VS Code extension](vscode.md)'s preview: a live view with no editor pane, where dragging still saves positions but files can't be written. It talks to the editor through `postMessage`. `--port 0` picks any free port.

`--diff-base REF` colours what changed since that ref, as [`build --diff-base`](#build) does, and keeps comparing as you edit: the ref is read once, at start.

## 8.4 export { #export }

```bash
qdbd export PATH... -o out.png|out.svg|out.drawio [-s …] [--focus TABLE --depth N] [--mode full|keys|header] [--regions] [--by-group] [--scale 2]
```

See [4.3 Exports](exports.md).

## 8.5 layout { #layout }

```bash
qdbd layout PATH... [--reset] [--by-group] [--layout FILE]
```

Writes positions to the layout file: placing new tables, re-laying out everything (`--reset`), or grouping by file / folder (`--by-group`). See [3.4 Table Positions](layout.md).

## 8.6 path { #path }

```bash
qdbd path PATH... --from TABLE --to TABLE
```

Prints the shortest relationship path and a SQL `FROM … JOIN … ON …` snippet. Exits 1 when the tables aren't connected.

A composite foreign key joins on every column: a DBML `Ref: a.(x, y) > b.(x, y)`, or QuickDBD FK lines that together point at all of a table's composite primary key. Between two tables with several relationships, one with join columns wins over a table-level `rel`. Dotted names such as `sales.orders` come out as `schema.table`.

## 8.7 diff { #diff }

```bash
qdbd diff OLD NEW
qdbd diff --base GIT_REF PATH... [--format text|markdown|json] [-o FILE] [--exit-code]
```

See [6. Reviewing Changes](diffs.md).

## 8.8 import dbt { #import-dbt }

```bash
qdbd import dbt target/manifest.json -o erd/ [--catalog FILE] [--package NAME] [--select GLOB] [--no-sources] [--infer-fks] [--check]
```

See [5.1 dbt Import](dbt.md).

## 8.9 share { #share }

```bash
qdbd share PATH... [-s SELECTOR] [--exclude SELECTOR] [--diff-base REF] [--by-group] [--layout FILE] [--public] [--new]
```

Builds the page like `build` and publishes it as a secret GitHub gist (with the `gh` CLI), then prints a link. Sharing the same files again updates the same gist. See [4.4 Sharing a Link](sharing.md).

## 8.10 convert { #convert }

```bash
qdbd convert PATH... --to dbml|quickdbd [-o FILE_OR_DIR]
```

Converts between QuickDBD text and DBML. With one file and no `-o`, prints the result; with `-o DIR`, writes each file under it with the new extension (DBML `TableGroup`s become one QuickDBD file each). Anything the target syntax can't express is a warning; the output is recompiled and must otherwise match the input, or nothing is written. See [3.2 DBML](dbml.md#convert).

## 8.11 mcp { #mcp }

```bash
qdbd mcp [PATH...] [--root DIR] [--infer-fks]
```

Runs an [MCP](https://modelcontextprotocol.io) server on stdin/stdout, so AI agents (Claude, Copilot, Cursor) can query the schema: tables, join paths with SQL, checks, diffs and diagrams. With no `PATH` it serves every schema project under `--root` (default: the project folder, else the current folder); with paths, just that schema or dbt `manifest.json`. It runs until the client closes it. See [3.7 AI Agents (MCP)](mcp.md).

## 8.12 Exit codes { #exit-codes }

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | schema errors, no matching tables, no path, or (`diff --exit-code`) changes found |
| 2 | bad arguments, missing files, git errors, or `share` upload errors |
