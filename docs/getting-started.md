# Getting Started

## Install

=== "pipx"

    ```bash
    pipx install quickdbd-cli
    ```

=== "uv"

    ```bash
    uv tool install quickdbd-cli
    # or run without installing:
    uvx --from quickdbd-cli qdbd --help
    ```

=== "pip"

    ```bash
    pip install quickdbd-cli
    ```

You need Python 3.11+. Everything else comes from pip.

## Write a schema

Create `schema.txt`. This is the same syntax you'd type into QuickDBD:

```text
Customer
-
CustomerId PK int
Name string
Email string UNIQUE

Order as o
----
OrderId PK int
CustomerId int FK >- Customer.CustomerId
OrderDate datetime
Total decimal(10,2)
```

A table is a name, a line of dashes, then one line per column: `name [type] [modifiers]`. `FK >- Customer.CustomerId` declares a many-to-one relationship. The [syntax reference](syntax.md) covers everything else.

## Check it

```bash
qdbd check schema.txt
```

```text
No errors found. Good job!
```

Errors print as `schema.txt:12: error: …` and exit with code 1, so the same command works as a CI gate.

## Edit it live

```bash
qdbd serve schema.txt
```

A browser tab opens with the diagram and an editor pane:

- Save in your own editor (or type in the pane, which autosaves) and the diagram reloads.
- **Drag tables** to arrange them. Positions are saved to `schema.layout.json`; commit it with the schema.
- New tables appear next to the tables they're related to, so your arrangement doesn't move.

## Build and share

```bash
qdbd build schema.txt -o schema.html
```

`schema.html` is one file. Email it, attach it, or publish it (the [GitHub Action](github-action.md) can do that). Click a table to see its details, filter with `orders+1`, or press **Link** to copy a URL to the exact view you're looking at.

## Many files

Point qdbd at a folder and every `*.txt` under it becomes one diagram. Foreign keys can cross files:

```bash
qdbd build schema/ -o schema.html
```

Each file becomes a group in the explorer sidebar and can get its own [region](reading-the-diagram.md#regions).

## Next

- [Reading the Diagram](reading-the-diagram.md): everything the page can do.
- [Worked example: jaffle_shop](example/index.md): the full flow on a dbt project.
