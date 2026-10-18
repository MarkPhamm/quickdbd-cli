# Schema Syntax

qdbd reads [QuickDBD](https://www.quickdatabasediagrams.com)'s text format. It mirrors QuickDBD's own parser, so a schema that works there works here, with the same error messages.

## Tables

```text
# Doc comment for the table
Customer as c, cust      # aliases, comma-separated
-                        # separator: any number of dashes
CustomerId PK int
Name string
```

- A table is a header line, a separator line of `-`, then column lines. A **blank line ends a table**; comment lines don't.
- Names with spaces or dots must be quoted: `"Product Catalog"`, `"dbo.Customer"`.
- Aliases can be used anywhere a table name is referenced.

## Columns

```text
name [type] [modifiers…]      # any order, case-insensitive
```

| Token | Meaning |
|---|---|
| `int`, `varchar(200)`, `decimal(10,2)` | the type: the first word that isn't a keyword |
| `PK` | primary key (several `PK` columns = composite key) |
| `FK` | foreign key, optionally followed by a relationship: `FK >- Customer.CustomerId` |
| `NULL` / `NULLABLE` | nullable. Columns are NOT NULL by default |
| `UNIQUE`, `INDEX` | unique key, index |
| `IDENTITY` / `AUTOINCREMENT` | auto-generated |
| `default=value`, `int=27`, `string="two words"` | default value |

PK can't be combined with UNIQUE or INDEX, and UNIQUE can't be combined with INDEX.

## Relationships

| Operator | Left → right |
|---|---|
| `-` | one to one |
| `-<` | one to many |
| `>-` | many to one |
| `>-<` | many to many |
| `-0` | one to zero-or-one |
| `0-` | zero-or-one to one |
| `0-0` | zero-or-one to zero-or-one |
| `-0<` | one to zero-or-many |
| `>0-` | zero-or-many to one |

Inline, on the column that holds the key:

```text
CustomerId int FK >- Customer.CustomerId
```

Table-level, between the header and the separator (no columns specified):

```text
OrderLine
rel >- Product
---
```

Targets can be aliases; quoted names work in targets too: `FK >- "dbo.Customer"."Customer Id"`. A relationship may be declared once (in either direction).

## Comments

`#` starts a comment, except inside double quotes. Comment lines directly above a table or column, plus a comment at the end of its line, become its **documentation**, shown as a tooltip and in the details panel.

## Settings and layout sections

```text
[settings]
Zoom 100
CaseSensitive on
DefaultFieldType int

[layout]
Customer 120 80
```

- `CaseSensitive` controls name lookups (off by default).
- `DefaultFieldType` is used for columns without a type.
- `[layout]` positions (from QuickDBD) are used for tables the [layout file](layout.md) doesn't cover.

## Where qdbd is more forgiving

qdbd accepts a few things QuickDBD rejects, and prints a **warning** for each:

- tab characters
- spaces inside a type: `decimal(10, 2)`
- an explicit `NOT NULL`
- indented table names
- `[layout]` lines for unknown tables

`qdbd check --strict` turns these into errors, so a file that passes is guaranteed to paste back into QuickDBD.

One difference isn't a warning: `default=` values keep their case, where QuickDBD lowercases them.

## Many files

Every file is parsed on its own; then all tables share one namespace, so foreign keys can point across files. Defining the same table in two files is an error that names both locations.
