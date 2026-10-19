# 6. Reviewing Schema Changes

## 6.1 Compare two versions { #compare-two-versions }

```bash
qdbd diff old.txt new.txt                 # two files or folders
qdbd diff --base origin/main erd/         # a git ref vs the working tree
```

With `--base`, qdbd reads the schema files as they were at that ref through `git show`; nothing is checked out.

Tables match by name, columns by name within a table, and relationships by their two endpoints. The report lists:

- tables added and removed;
- per table: columns added, removed, and changed (type, PK, FK, NULL, UNIQUE, INDEX, IDENTITY, default);
- relationships added and removed, written `child.col -> parent.col (N:1)`.

| Option | |
|---|---|
| `--format text` | the default, for terminals |
| `--format markdown` | for PR comments (what the [GitHub Action](github-action.md) posts) |
| `--format json` | for scripts |
| `-o FILE` | write to a file |
| `--exit-code` | exit 1 when anything changed, like `git diff --exit-code` |

## 6.2 See the changes in the diagram { #see-the-changes-in-the-diagram }

```bash
qdbd build erd/ --diff-base origin/main -o erd.html
```

- **NEW** tables: green header. **CHANGED** tables: amber header.
- Added and changed columns: a coloured bar at the row's edge.
- A banner shows the counts; **Show changes** filters to `diff:modified` plus neighbours.
- The details panel lists each change, including removed columns.

The `diff:` [selector](selectors.md) (`diff:modified`, `diff:added`, `diff:changed`) works with `-s` and in the page.
