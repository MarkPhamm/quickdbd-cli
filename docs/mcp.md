# 3.7 AI Agents (MCP)

`qdbd mcp` gives AI agents your schema. Claude Code, Claude Desktop, Cursor, VS Code's Copilot and any other [MCP](https://modelcontextprotocol.io) client can then ask qdbd about tables, keys and joins, instead of guessing from the raw files.

The agent gets the compiled schema: every table and column, relationships with their cardinality, docs and tags, across all your files. It can:

- **explain the schema**: list, search and describe tables;
- **write SQL with the right joins**: the join path between two tables, with a `FROM … JOIN … ON …` clause that joins composite keys on every column, and notes on optional and row-multiplying joins;
- **edit schema files safely**: read the syntax, then check its edits, even before saving them;
- **review changes**: what a branch changed, compared from where it left `main`;
- **show a diagram**: a PNG of the tables in question.

Every tool only reads. The server runs on your machine and talks to the agent over stdin/stdout.

## Set it up

You need qdbd 0.3.0 or later ([1. Install](install.md)).

=== "Claude Code"

    In your project folder:

    ```bash
    claude mcp add qdbd -- qdbd mcp
    ```

    Or commit a `.mcp.json` so your whole team gets it:

    ```json
    {
      "mcpServers": {
        "qdbd": { "command": "qdbd", "args": ["mcp"] }
      }
    }
    ```

=== "VS Code (Copilot)"

    With the [QuickDBD extension](vscode.md) (VS Code 1.101 or later), there is nothing to set up: agent mode lists a **QuickDBD** server for each workspace folder with a schema.

    Without the extension, add `.vscode/mcp.json`:

    ```json
    {
      "servers": {
        "qdbd": { "type": "stdio", "command": "qdbd", "args": ["mcp", "--root", "${workspaceFolder}"] }
      }
    }
    ```

=== "Cursor"

    Add `.cursor/mcp.json` to the project:

    ```json
    {
      "mcpServers": {
        "qdbd": { "command": "qdbd", "args": ["mcp", "--root", "${workspaceFolder}"] }
      }
    }
    ```

=== "Claude Desktop"

    Claude Desktop doesn't start servers in your project, so name the folder. In **Settings → Developer → Edit Config**:

    ```json
    {
      "mcpServers": {
        "qdbd": { "command": "qdbd", "args": ["mcp", "--root", "/path/to/your/project"] }
      }
    }
    ```

=== "Without installing"

    Any client can start it through [uv](https://docs.astral.sh/uv/):

    ```json
    { "command": "uvx", "args": ["--from", "quickdbd-cli>=0.3", "qdbd", "mcp"] }
    ```

    The first start downloads qdbd, which can be slow enough to hit a client's startup timeout. `uv tool install quickdbd-cli` (or `pipx install quickdbd-cli`) avoids that.

If `qdbd` isn't on the client's `PATH`, give the full path to it as the `command`: `which qdbd` prints it.

## Which schema it reads

With no path, `qdbd mcp` finds every schema project under the project folder, the same way the [VS Code sidebar](vscode.md) does:

- a schema file with its own layout file, a folder with a `qdbd.layout.json`, a folder where every `.txt` is a schema, or a single schema file;
- a dbt project: a `dbt_project.yml` with `target/manifest.json` beside it (run `dbt compile` first; `dbt docs generate` adds column types). It's read in memory: nothing is written.

It skips hidden folders, `node_modules`, `venv`, `target`, `build` and the like. With several projects, the agent calls `list_projects` and passes a `project` to the other tools.

The project folder is `--root DIR` if given, else the folder Claude Code says is the project (`CLAUDE_PROJECT_DIR`), else the current folder. qdbd won't search your whole disk or home folder: start it with `--root` there.

To serve one schema only, name it, as with the other commands:

```bash
qdbd mcp schema/                  # a folder of schema files
qdbd mcp shop.dbml
qdbd mcp target/manifest.json     # a dbt project
```

### dbt projects with few relationships

Many dbt projects declare few `relationships` tests, so the agent finds no join between models. `qdbd mcp --infer-fks` also links `<entity>_id` columns to the model named after the entity, like [`qdbd import dbt --infer-fks`](dbt.md). Those joins are marked "inferred from column names" wherever the agent sees them.

## The tools

| Tool | What the agent gets |
|---|---|
| `list_projects` | The schema projects found: files, table and relationship counts, errors. |
| `list_tables` | Every table, or those matching a [selector](selectors.md), with column counts and the first line of each doc. |
| `describe_tables` | Columns (type, keys, foreign key target, null, default, docs) and each table's relationships with cardinality. |
| `search_schema` | Tables, columns and docs that mention a word, e.g. `email`. |
| `join_path` | The join chain between two tables and its SQL, with notes: "optional: LEFT JOIN keeps rows without a match", "1:N: rows multiply", and other relationships between the same tables. |
| `check_schema` | `qdbd check` for the project, or for unsaved text the agent wants to write. |
| `diff_schema` | What changed since a git ref: since the branch left `main`, or uncommitted changes. |
| `render_diagram` | A PNG of some tables: up to about 30 with their columns, more as keys or headers only. |
| `syntax_reference` | How to write QuickDBD or DBML text, for edits. |

Answers are short plain text, written to save the agent's context. A long answer says what it left out and how to narrow the question.

## Things to ask

- "Which tables hold customer data, and how do orders join to them?"
- "Write a query for revenue per customer per month."
- "Add a `refunds` table linked to `payments`, then check the schema."
- "What did this branch change in the schema? Anything risky?"
- "Show me the diagram around `orders`."

## Privacy

The schema stays on your machine, but what a tool returns goes to your AI provider as part of the conversation: table and column names, docs, and the files' text when the agent reads them. qdbd ignores symbolic links that point outside the project folder.

## Troubleshooting

- **The client says the server failed to start.** Run `qdbd mcp` in a terminal: it should print one line on stderr and wait. `qdbd: error: argument cmd: invalid choice: 'mcp'` means an older qdbd: upgrade it ([1.4 Upgrading](install.md)).
- **"no schema files found"**: the server started in the wrong folder. Pass `--root /path/to/project`.
- **Errors look odd:** qdbd's messages show a name's non-alphanumeric characters as character codes, so `dbo46Order32Line` is `dbo.Order Line`.
- **To see what the agent sees,** try the [MCP Inspector](https://github.com/modelcontextprotocol/inspector): `npx @modelcontextprotocol/inspector qdbd mcp`.

`qdbd mcp` speaks both the current MCP protocol (2026-07-28) and the earlier ones (2024-11-05 to 2025-11-25), so older clients work too.
