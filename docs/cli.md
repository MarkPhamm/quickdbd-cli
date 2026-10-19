# 8. CLI Reference

Every command takes one or more `PATH`s: a `.txt` file, or a folder (every `*.txt` under it, recursively). `qdbd <command> --help` shows all options.

## 8.1 check { #check }

```bash
qdbd check PATH... [--strict]
```

Validates the schema. Prints `No errors found. Good job!`, or `file:line: error: message` lines and exits 1. `--strict` also fails on [QuickDBD-compatibility warnings](syntax.md#where-qdbd-is-more-forgiving).

## 8.2 build { #build }

```bash
qdbd build PATH... -o diagram.html [-s SELECTOR] [--exclude SELECTOR] [--diff-base REF] [--by-group] [--layout FILE] [--strict]
```

Writes one self-contained HTML page. Builds are deterministic (same input, same bytes), and the layout file is read but never written.

## 8.3 serve { #serve }

```bash
qdbd serve PATH... [--port 8765] [--layout FILE] [--no-open] [--read-only]
```

Local live editor on `127.0.0.1`: reloads when files change, browser editor pane with autosave, drag tables to save positions. Ctrl+C stops it.

The default port is 8765. If it's busy (for example, a second `qdbd serve` is running), the next free port is used and printed. An explicit `--port` that's busy is an error.

`--read-only` serves a live view with no editor that never writes to disk, safe to put behind a tunnel ([4.4 Sharing a Link](sharing.md#live-read-only-link)).

## 8.4 export { #export }

```bash
qdbd export PATH... -o out.png|out.svg|out.drawio [-s …] [--focus TABLE --depth N] [--mode full|keys|header] [--regions] [--by-group] [--scale 2]
```

See [4.3 Exports](exports.md).

## 8.5 layout { #layout }

```bash
qdbd layout PATH... [--reset] [--by-group] [--layout FILE]
```

Writes positions to the layout file: placing new tables, re-laying out everything (`--reset`), or grouping by file / folder (`--by-group`). See [3.3 Table Positions](layout.md).

## 8.6 path { #path }

```bash
qdbd path PATH... --from TABLE --to TABLE
```

Prints the shortest relationship path and a SQL `FROM … JOIN … ON …` snippet. Exits 1 when the tables aren't connected.

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

## 8.10 Exit codes { #exit-codes }

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | schema errors, no matching tables, no path, or (`diff --exit-code`) changes found |
| 2 | bad arguments, missing files, git errors, or `share` upload errors |
