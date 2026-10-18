# 4. Automate in CI

Add one workflow and every pull request gets a schema-diff comment, plus the diagram with the changes highlighted.

```yaml title=".github/workflows/erd.yml"
name: ERD
on: [pull_request, push]

jobs:
  erd:
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write }
    steps:
      - uses: actions/checkout@v4
      # ... your dbt setup: dbt deps && dbt build && dbt docs generate
      - run: pipx run --spec quickdbd-cli qdbd import dbt target/ -o erd/
      - uses: MarkPhamm/quickdbd-cli@v0.1.5
        with:
          path: erd/
          output: site/index.html
```

On a pull request the action:

1. checks the schema (`qdbd check`) and fails the job on errors;
2. builds `site/index.html` with `--diff-base origin/<base>` and uploads it as the **erd** artifact;
3. posts **one** comment with the diff, and updates the same comment on later pushes.

The comment looks like this:

> ### Schema changes: `origin/main` → `working tree`
>
> **1 table(s) added, 0 removed, 1 changed; 1 relationship(s) added, 0 removed**
>
> #### ➕ Tables added
> - `payments`
>
> #### ✏️ Tables changed
> | Table | Change |
> |---|---|
> | `customers` | ➕ `loyalty_tier` |

## Publish the diagram

To keep an always-current ERD on GitHub Pages, add a deploy job. This site's own [`.github/workflows/erd.yml`](https://github.com/MarkPhamm/quickdbd-cli/blob/main/.github/workflows/erd.yml) does exactly that for the [demo](../demo/).

```yaml
      - if: github.event_name == 'push'
        uses: actions/upload-pages-artifact@v3
        with: { path: site }

  pages:
    if: github.event_name == 'push'
    needs: erd
    runs-on: ubuntu-latest
    permissions: { pages: write, id-token: write }
    environment: { name: github-pages, url: "${{ steps.deploy.outputs.page_url }}" }
    steps:
      - id: deploy
        uses: actions/deploy-pages@v4
```

All inputs are in [GitHub Action](../github-action.md).
