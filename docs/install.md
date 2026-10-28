# 1. Install

## 1.1 Install the CLI { #install-the-cli }

Install with [pipx](https://pipx.pypa.io), [uv](https://docs.astral.sh/uv/) or pip:

=== "pipx"

    ```bash
    pipx install quickdbd-cli
    ```

=== "uv"

    ```bash
    uv tool install quickdbd-cli
    ```

=== "pip"

    ```bash
    pip install quickdbd-cli
    ```

You need **Python 3.11+** on macOS, Linux or Windows; `python3 --version` shows yours. Nothing else: no Graphviz, Node or browser. Layout uses the [Eclipse Layout Kernel](https://eclipse.dev/elk/) in an embedded JavaScript engine that comes with the package.

## 1.2 Check it works { #check-it-works }

```bash
qdbd --version
```

!!! tip "`qdbd: command not found`?"
    `pip install` put the `qdbd` script in a folder that isn't on your `PATH`. Either install with `pipx` (it manages `PATH` for you), or find the script with `python -m pip show -f quickdbd-cli` and add its folder to `PATH`.

## 1.3 Try it without installing { #try-it-without-installing }

With [uv](https://docs.astral.sh/uv/), prefix any command with `uvx --from quickdbd-cli`:

```bash
uvx --from quickdbd-cli qdbd build schema.txt -o schema.html
```

## 1.4 Upgrade { #upgrade }

```bash
pipx upgrade quickdbd-cli        # or: uv tool upgrade quickdbd-cli / pip install -U quickdbd-cli
```

## 1.5 VS Code, Cursor and others { #vs-code }

Prefer an editor to a terminal? Install the **QuickDBD (qdbd)** extension, from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=MarkPhamm.quickdbd) for VS Code or from [Open VSX](https://open-vsx.org/extension/MarkPhamm/quickdbd) for Cursor, Windsurf and VSCodium. It installs the CLI for you. See [3.6 Editing in VS Code](vscode.md).

Next: [2. Quick Start](getting-started.md), your first diagram in 5 minutes.
