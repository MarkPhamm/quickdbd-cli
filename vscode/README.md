# QuickDBD (qdbd) for VS Code

Edit [QuickDBD](https://www.quickdatabasediagrams.com) schema files with the interactive ER diagram beside you. Powered by the [`qdbd`](https://github.com/MarkPhamm/quickdbd-cli) CLI, so what you see matches `qdbd check`, `qdbd build` and QuickDBD itself.

![A schema on the left, the live diagram on the right with the table under the cursor selected](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/vscode.png)

## Features

- **Highlighting** for tables, columns, types, keys, relationships and comments.
- **Errors as you type**: squiggles and the Problems panel, with QuickDBD's own error messages. Unsaved text is checked against the rest of the schema.
- **Outline and go to definition**: tables and columns in the Outline view and breadcrumbs; **F12** on `Customer.CustomerId` jumps to it, across files.
- **The diagram beside the editor**: **Cmd/Ctrl+K V**. It follows your cursor, updates on save, and follows your theme. Double-click a table to jump to it; drag to arrange (saved to the layout file).
- **Export and share**: PNG, SVG, editable draw.io, or a gist link.

## Requirements

The `qdbd` CLI, version 0.1.16 or later:

```bash
uv tool install quickdbd-cli      # or: pipx install quickdbd-cli
```

The extension finds it in the `quickdbd.qdbdPath` setting, the workspace's `.venv`, or your `PATH`.

## Which files

QuickDBD files are `.txt`. A `.txt` file opens as QuickDBD when it has a table with a `PK`, `FK` or `rel` line, or a `qdbd.layout.json` / `<name>.layout.json` next to it. `files.associations` works too.

Full documentation: [qdbd.dev/vscode](https://qdbd.dev/vscode/).
