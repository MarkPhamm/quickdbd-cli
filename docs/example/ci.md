# 5.6 Step 4: Automate in CI

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
      - uses: MarkPhamm/quickdbd-cli@v0.4.0
        with:
          dbt-manifest: target/
          dbt-args: --infer-fks
          path: erd/
          output: site/index.html
```

The action regenerates `erd/` from the manifest, then on a pull request it:

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

Commit `erd/` (step 1) so the action can compare the pull request's schema with `main`'s. To make sure nobody forgets to re-run the import, use `dbt-check: true` instead: the action then fails when the committed files are out of date, rather than regenerating them.

## Publish the diagram

!!! warning "A Pages site is public unless you restrict it"
    Anyone can open a GitHub Pages site, unless it's published from a private or internal repository of an organisation on GitHub Enterprise Cloud with [access control](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site) turned on. Publish a client's schema only where their agreement allows it. Publishing means you accept the [disclaimer](../sharing.md#disclaimer).

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

All inputs are in [7.2 Inputs](../github-action.md#inputs).
