# 3.2 DBML

qdbd also reads [DBML](https://dbml.dbdiagram.io/docs/), the schema language of [dbdiagram.io](https://dbdiagram.io). A DBML file works everywhere a QuickDBD file does (`check`, `build`, `serve`, `export`, `path`, `diff`, `share`, the [GitHub Action](github-action.md) and the [VS Code extension](vscode.md)), with no conversion step:

```dbml
Table customers {
  id int [pk, increment]
  email varchar [unique, not null]
  Note: 'Anyone who has bought something.'
}

Table orders {
  id int [pk]
  customer_id int [ref: > customers.id]
  placed_at timestamp [default: `now()`]
}
```

```bash
qdbd build shop.dbml -o shop.html
```

The [Event ticketing demo](https://qdbd.dev/demo/ticketing/) is written in DBML.

## Which files are DBML

- A `.dbml` file is always DBML.
- A `.txt` file is DBML when it has a DBML declaration: a line like `Table name {`, `Enum name {`, `TableGroup name {`, `Project {`, or `Ref:` followed by a relationship. Anything else is read as QuickDBD, as before.

The whole file decides, so one broken line still gets DBML's error messages rather than QuickDBD's. No valid QuickDBD file looks like DBML (a QuickDBD table name can't be followed by `{`).

## What qdbd accepts, and what it draws

The reference is dbdiagram.io's own parser, [@dbml/parse](https://github.com/holistics/dbml/tree/master/packages/dbml-parse) 10.3.1: its test suite runs in qdbd's, so a file it accepts is accepted here, and a file it rejects is an error here too, on the same line.

**Drawn:**

| DBML | In the diagram |
|---|---|
| `Table name as alias`, `schema.table` | a table; `public.users` and `users` are the same table |
| columns, types (`varchar(255)`, `int[]`, `"double precision"`) | columns |
| `pk`, `primary key`, `indexes { (a, b) [pk] }` | key icon |
| `null`, `unique`, `increment`, `default:`, single-column `[unique]` indexes | badges |
| other indexes (composite, `[name: ...]`) | `index` badge on each column |
| `note:` and `Note` on tables and columns | tooltips and the details panel |
| `Ref:` in every form: short, long `{ }`, inline `[ref: ...]`, composite `a.(x, y) > b.(x, y)`, cross-schema | links; a composite ref draws one line per column pair |
| `<`, `>`, `-`, `<>`, and `?` for an optional side (`>?`, `?-`, `<>?`, ...) | [crow's-foot ends](reading-the-diagram.md), with a circle on an optional end |
| `TableGroup` | explorer groups, regions and `--by-group` |
| `headercolor` | the table's header colour (diff colours still win) |
| `TablePartial` and `~partial` | the partial's columns, settings and indexes, merged as dbdiagram.io does |

**Accepted but not drawn:** `Project`, `Enum` (the column shows the enum's name as its type), `checks`, `records`, sticky notes, `Dep` lineage, `Metadata`, `DiagramView`, `[inactive]` refs, ref `delete:`/`update:`/`color:`, `TableGroup` colours and notes.

**`use` and `reuse`:** qdbd reads every file you give it into one namespace, so it doesn't follow imports. A `use` line is a warning: pass the imported file (or its folder) too. An import that renames a table (`as`) is an error.

## Tags and colours

[Name-prefix tags](tags.md) (`dim_`, `fct_`, …) work on DBML tables. The comment directives work with `//`:

```dbml
// @color hot #ff5722
// @tag: hot, pii
Table customers {
  id int
  email varchar // @tag: pii
}
```

Plain `//` comments are not documentation in DBML; use `Note` / `note:`.

## Mixing DBML and QuickDBD

One folder can hold both. All tables share one namespace ([3.3](files.md)): a QuickDBD `FK >- customers.id` can point at a table defined in a `.dbml` file, and a DBML `Ref:` at one defined in a `.txt` file. Each file is one syntax or the other.

## Converting { #convert }

```bash
qdbd convert shop.dbml --to quickdbd            # prints the QuickDBD text
qdbd convert schema/ --to dbml -o schema-dbml/  # a folder: same file names, new extension
```

The output is recompiled before anything is written, and must give the same tables, columns, keys and links as the input. Whatever the target syntax can't express is reported as a warning, with its line:

| From | To | Not carried over |
|---|---|---|
| QuickDBD | DBML | table-level links (`rel >- Product`, kept as a `//` comment), a second alias, `[settings]` zoom and position. `[layout]` positions go to the [layout file](layout.md) beside the output. |
| DBML | QuickDBD | header colours, enums (kept as a `#` comment listing the values), checks, records, composite and expression indexes (drawn as `INDEX` on each column), ref settings, sticky notes, `Project`, the optional (`?`) operators QuickDBD has no symbol for (made required). |

With `-o DIR`, DBML `TableGroup`s become one QuickDBD file each (tables outside any group stay in a file named after the source), since QuickDBD groups tables by file. To a single file, groups are dropped with a warning.

In VS Code, **QuickDBD: Convert to DBML** and **Convert to QuickDBD Syntax** do the same from the editor, a schema's row in the sidebar, or the sidebar's **Actions**.
