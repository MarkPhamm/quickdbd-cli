# QuickDBD (qdbd) for VS Code

Edit [QuickDBD](https://www.quickdatabasediagrams.com) and [DBML](https://dbml.dbdiagram.io/docs/) schema files with the interactive ER diagram beside you. Powered by the [`qdbd`](https://github.com/MarkPhamm/quickdbd-cli) CLI, so what you see matches `qdbd check`, `qdbd build` and QuickDBD itself.

![A schema on the left, the live diagram on the right with the table under the cursor selected](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/vscode.png)

[![Watch the 60-second qdbd demo video](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/demo-poster.jpg)](https://qdbd.dev/#demo)

## Features

- **A sidebar** (the QuickDBD icon in the Activity Bar) listing every schema in the workspace, down to each column's type and keys, with every action one click away.
- **Highlighting** for tables, columns, types, keys, relationships and comments.
- **Errors as you type**: squiggles and the Problems panel, with QuickDBD's own error messages. Unsaved text is checked against the rest of the schema.
- **Outline and go to definition**: tables and columns in the Outline view and breadcrumbs; **F12** on `Customer.CustomerId` jumps to it, across files.
- **The diagram beside the editor**: **Cmd/Ctrl+K V**. It follows your cursor, updates on save, and follows your theme. Double-click a table to jump to it; drag to arrange (saved to the layout file).
- **Open in Browser**: the schema on localhost in your browser, with the diagram and an editor side by side, as `qdbd serve` runs it.
- **Export**: PNG, SVG, editable draw.io, or the interactive diagram as one HTML page.
- **Share**: a secret gist link, signed in with VS Code's GitHub account. Off by default: turn on `quickdbd.allowSharing` first.
- **Compare with git**: the diagram coloured by what changed since a branch, tag or commit, updating as you save.
- **Import dbt**: schema files from a dbt project's `target/manifest.json`, opened with their diagram.
- **Convert** between QuickDBD and DBML, both ways, from the editor or the sidebar.
- **AI agent tools**: Copilot's agent mode gets your schema's tables, join paths with SQL, checks and diffs through [`qdbd mcp`](https://qdbd.dev/mcp/), with no setup (VS Code 1.101+).

![The QuickDBD sidebar: schemas, a table expanded to its columns with their types and keys, and the actions](https://raw.githubusercontent.com/MarkPhamm/quickdbd-cli/main/docs/assets/img/vscode-sidebar.png)

## Requirements

None to install by hand: the extension runs the `qdbd` CLI (0.2.0 or later; 0.3.0 for the AI agent tools), and when it's missing, **Install qdbd** sets it up in a Python environment of the extension's own. That needs Python 3.11+ or [uv](https://docs.astral.sh/uv/) on the machine.

If you already have `qdbd` (`uv tool install quickdbd-cli`), the extension uses it: the `quickdbd.qdbdPath` setting, else the workspace's `.venv`, else the newer of its own install and the one on your `PATH`.

## Which files

QuickDBD files are `.txt`. A `.txt` file opens as QuickDBD when it has a table with a `PK`, `FK` or `rel` line, or a `qdbd.layout.json` / `<name>.layout.json` next to it. DBML files are `.dbml`; a `.txt` holding DBML (a `Table name {` or `Ref:` line) opens as DBML. A folder can mix both. `files.associations` works too.

Full documentation: [qdbd.dev/vscode](https://qdbd.dev/vscode/).
