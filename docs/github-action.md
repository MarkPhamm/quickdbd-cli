# GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: MarkPhamm/quickdbd-cli@v0.1.4
  with:
    path: erd/
    output: site/index.html
```

The job needs `permissions: { contents: read, pull-requests: write }` for the PR comment.

## What it does

On every run:

1. installs qdbd from PyPI;
2. runs `qdbd check` and fails the job on errors (or warnings, with `strict: true`);
3. builds the HTML diagram and uploads it as the **erd** artifact.

On pull requests it also:

4. fetches the base branch and runs `qdbd diff --base origin/<base>`;
5. builds the diagram with `--diff-base`, so changes are highlighted;
6. posts **one** comment with the markdown diff, and updates that same comment on later pushes.

## Inputs

| Input | Default | |
|---|---|---|
| `path` | required | schema files or folders, space-separated |
| `output` | `erd/index.html` | where to write the HTML |
| `check` | `true` | fail on schema errors |
| `strict` | `false` | also fail on QuickDBD-compatibility warnings |
| `comment` | `true` | post the diff comment on pull requests |
| `select` | | [selector](selectors.md) for the diagram |
| `upload-artifact` | `true` | upload the HTML as `erd` |
| `qdbd-version` | `latest` | PyPI version to install |
| `python-version` | `3.12` | |
| `github-token` | `${{ github.token }}` | token for the comment |

## Outputs

| Output | |
|---|---|
| `html` | path of the built page |
| `changed` | `"true"` when the pull request changes the schema |
| `diff-file` | markdown diff (pull requests) |

## Publishing to GitHub Pages

Upload `output`'s folder with `actions/upload-pages-artifact` and deploy it with `actions/deploy-pages` on pushes to your main branch. The [worked example](example/ci.md#publish-the-diagram) has the full workflow.

## With dbt

Run your dbt build and `qdbd import dbt` before the action; see the [worked example](example/ci.md).

## Not on GitHub?

The action only wraps the CLI. For example, on GitLab:

```yaml
erd:
  image: python:3.12
  script:
    - pip install quickdbd-cli
    - qdbd check erd/
    - qdbd build erd/ -o public/index.html
  artifacts:
    paths: [public/index.html]
```

There is also a [pre-commit](https://pre-commit.com) hook:

```yaml
repos:
  - repo: https://github.com/MarkPhamm/quickdbd-cli
    rev: v0.1.4
    hooks:
      - id: qdbd-check
        files: ^erd/.*\.txt$
```
