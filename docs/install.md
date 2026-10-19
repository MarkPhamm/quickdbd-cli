# 1. Install

## 1.1 Install the CLI { #install-the-cli }

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

You need **Python 3.11+**. Nothing else: no Graphviz, Node or browser. Layout uses the [Eclipse Layout Kernel](https://eclipse.dev/elk/) in an embedded JavaScript engine that comes with the package.

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

Next: [2. Quick Start](getting-started.md), your first diagram in 5 minutes.
