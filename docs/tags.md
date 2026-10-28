# 3.5 Tags and Colours

Tags group tables by role (dim, fact, staging, …) and give each group its own header colour. Every tag is written as a comment, so the file still pastes into QuickDBD unchanged.

```text
# @color gold #b8860b

# @tag: gold, pii
customers
-
customer_id PK int

dim_date            # tagged "dim" from its name
-
date_key PK int
```

## Where tags come from

A table's tags come from the **first** of these that gives it any:

| Priority | Source | Example |
|---|---|---|
| 1 | an explicit `# @tag:` comment above the table (or at the end of its name line) | `# @tag: gold, pii` |
| 2 | the table's name | `dim_customer` → `dim` |
| 3 | dbt tags, written by [`qdbd import dbt`](dbt.md) | `# @dbt-tags: nightly, finance` |

So an explicit tag overrides the name, and the name overrides dbt's tags. `@tag` and `@tags` both work; separate several tags with commas or spaces. Tag names are case-insensitive.

### Tags from names

| Tag | Names |
|---|---|
| `dim` | `dim_customer`, `DimCustomer` |
| `fact` | `fct_orders`, `fact_sales`, `FactSales` |
| `staging` | `stg_orders`, `stg_shop__orders`, `StgOrders` |
| `intermediate` | `int_orders_pivoted` |
| `raw` | `raw_orders`, `src_orders`, `jaffle_shop.raw_orders` |

The prefix is also recognised after a source name (`jaffle_shop.raw_orders`) or a dbt double underscore (`conformed__dim_airline`).

## Colours

The header takes the colour of the table's **first** tag. Untagged tables stay blue.

| Tag | Default |
|---|---|
| `dim` | <span style="color:#00838f">■</span> `#00838f` teal |
| `fact` | <span style="color:#c2185b">■</span> `#c2185b` raspberry |
| `staging` | <span style="color:#546e7a">■</span> `#546e7a` slate |
| `intermediate` | <span style="color:#7b1fa2">■</span> `#7b1fa2` purple |
| `raw` | <span style="color:#6d4c41">■</span> `#6d4c41` brown |

Other tags get colours from a fixed palette, in alphabetical order of tag name, so the same schema always gets the same colours. To pick your own, add a comment line anywhere in any file:

```text
# @color dim #2e7d32
# @color gold #b8860b
```

The value must be a `#rgb` or `#rrggbb` hex colour; anything else is a warning. If two files set different colours for the same tag, the first file (in sorted order) wins, with a warning. The defaults avoid green and amber, which [diff views](diffs.md) use for new and changed tables; in a diff view those colours take precedence.

## Column tags { #columns }

A `# @tag:` comment on a column line, or on the line above it, tags that **column**. The row gets a tint, a bar and a name in the tag's colour. It's made for proposing column changes in a review: mark what you're adding and removing, and reviewers see both at a glance. Column tags need qdbd 0.3.1 or later ([1.4 Upgrade](install.md#upgrade)).

```text
orders
-
id PK int
customer_id int FK >- customers.id
discount_pct decimal     # @tag: added
legacy_code varchar      # @tag: removed
# @tag: pii
email varchar
```

| Tag | Default | Drawn as |
|---|---|---|
| `added` | <span style="color:#2e7d32">■</span> `#2e7d32` green | green row |
| `removed` | <span style="color:#c62828">■</span> `#c62828` red | red row, name struck through |

Any other tag works too, with its colour from `# @color` or the palette, as for tables. Column tags don't change the table's header colour. They show in the legend (the count is the number of tables that carry the tag), `tag:removed` selects the tables that have such a column, and the **Keys** view (`--mode keys`) keeps tagged columns visible. In DBML, use `// @tag:` at the end of the column line.

Hand-tagging is for proposals. To get added and changed columns from git automatically, use [`--diff-base`](diffs.md).

## In the page

- **Legend:** under the filter box, one chip per tag with its colour and table count. Click a chip to show only that tag; click it again to clear.
- **Explorer:** a coloured dot before each tagged table.
- **Details panel:** the table's tags and each column's tags, as clickable chips.
- **Minimap and exports:** PNG, SVG and draw.io keep the header colours.

## Selecting by tag

`tag:` works like dbt's tag selector, in the page's filter box and with `-s`:

```bash
qdbd build erd/ -s 'tag:fact+1' -o facts.html     # fact tables and the tables they reference
qdbd export erd/ -s 'tag:dim' -o dims.png
```

See [4.2 Selecting Tables](selectors.md).
