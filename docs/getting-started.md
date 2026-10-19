# 2. Quick Start

Your first diagram in 5 minutes. You need qdbd [installed](install.md).

## 2.1 Write (or paste) a schema { #write-a-schema }

Save this as `schema.txt`. If you already have a schema in QuickDBD, copy it from QuickDBD's editor and paste it in unchanged.

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

A table is a name, a line of dashes, then one column per line: `name type modifiers`. `FK >- Customer.CustomerId` means *many orders → one customer*. Everything else is in [3.1 Schema Syntax](syntax.md).

## 2.2 Check it { #check-it }

```bash
qdbd check schema.txt
```

```text
No errors found. Good job!
```

Errors print as `schema.txt:12: error: …`, using QuickDBD's own messages, and exit with code 1. That makes the same command a CI gate ([7. CI and Automation](github-action.md)).

## 2.3 Edit it live { #edit-it-live }

```bash
qdbd serve schema.txt
```

A browser tab opens with the diagram and an editor pane.

- **Edit** in the pane (it autosaves 1 s after you stop typing) or in your own editor. The diagram reloads on save.
- **Drag tables** to arrange them. Positions are saved to `schema.layout.json`; commit it with the schema ([3.3 Table Positions](layout.md)).
- **Stop** the server with ++ctrl+c++.

## 2.4 Build a page to share { #build-and-share }

```bash
qdbd build schema.txt -o schema.html
```

`schema.html` is one self-contained file. Open it locally, email it, attach it to a ticket, or publish it on GitHub Pages ([7.4](github-action.md#publishing-to-github-pages)). To send a **link** instead, run `qdbd share schema.txt` ([4.4 Sharing a Link](sharing.md)).

In the page, click a table to see its details, type `+Order` in the filter, or press **Link** to copy a URL to exactly what you're looking at. The tour is in [4.1 Reading the Diagram](reading-the-diagram.md).

## 2.5 Export an image { #export-an-image }

```bash
qdbd export schema.txt -o schema.png                         # whole diagram: .png, .svg or .drawio
qdbd export schema.txt --focus Order --depth 1 -o order.svg   # one table and its neighbours
```

`.drawio` files open in [diagrams.net](https://app.diagrams.net) as editable ER shapes. More: [4.3 Exports](exports.md).

## 2.6 Where next { #next }

| You want to… | Go to |
|---|---|
| Split a big schema into several files | [3.2 Many Files, One Diagram](files.md) |
| Filter to part of the schema, or find how two tables join | [4.2 Selecting Tables](selectors.md), [4.1 Reading the Diagram](reading-the-diagram.md#details-panel) |
| Generate the schema from a dbt project | [5.1 dbt Import](dbt.md) |
| Send someone a link to the diagram | [4.4 Sharing a Link](sharing.md) |
| See what a branch changes | [6. Reviewing Changes](diffs.md) |
| Run it on every pull request | [7. CI and Automation](github-action.md) |
