# The qdbd CLI

Every command takes one or more `PATH`s: a `.txt` file, or a folder (every `*.txt` under it, recursively). `qdbd <command> --help` shows all options.

## check

```bash
qdbd check PATH... [--strict]
```

Validates the schema. Prints `No errors found. Good job!`, or `file:line: error: message` lines and exits 1. `--strict` also fails on [QuickDBD-compatibility warnings](syntax.md#where-qdbd-is-more-forgiving).

## build

```bash
qdbd build PATH... -o diagram.html [-s SELECTOR] [--exclude SELECTOR] [--diff-base REF] [--by-group] [--layout FILE] [--strict]
```

Writes one self-contained HTML page. Builds are deterministic (same input, same bytes), and the layout file is read but never written.

## serve

```bash
qdbd serve PATH... [--port 8765] [--layout FILE] [--no-open]
```

Local live editor on `127.0.0.1`: reloads when files change, browser editor pane with autosave, drag tables to save positions. Ctrl+C stops it.

## export

```bash
qdbd export PATH... -o out.png|out.svg|out.drawio [-s …] [--focus TABLE --depth N] [--mode full|keys|header] [--regions] [--by-group] [--scale 2]
```

See [Exports](exports.md).

## layout

```bash
qdbd layout PATH... [--reset] [--by-group] [--layout FILE]
```

Writes positions to the layout file: placing new tables, re-laying out everything (`--reset`), or grouping by file / folder (`--by-group`). See [Table Positions](layout.md).

## path

```bash
qdbd path PATH... --from TABLE --to TABLE
```

Prints the shortest relationship path and a SQL `FROM … JOIN … ON …` snippet. Exits 1 when the tables aren't connected.

## diff

```bash
qdbd diff OLD NEW
qdbd diff --base GIT_REF PATH... [--format text|markdown|json] [-o FILE] [--exit-code]
```

See [Schema Diffs](diffs.md).

## import dbt

```bash
qdbd import dbt target/manifest.json -o erd/ [--catalog FILE] [--package NAME] [--select GLOB] [--no-sources]
```

See [dbt Import](dbt.md).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | schema errors, no matching tables, no path, or (`diff --exit-code`) changes found |
| 2 | bad arguments, missing files, or git errors |
