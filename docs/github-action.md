# 7. CI and Automation

qdbd is a plain CLI, so it runs in any CI. On GitHub, the action below does the whole job; elsewhere, see [7.6](#not-on-github).

## 7.1 GitHub Action { #github-action }

Add this file to your repo:

```yaml title=".github/workflows/erd.yml"
name: ERD
on: [pull_request, push]
jobs:
  erd:
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write }   # write: for the PR comment
    steps:
      - uses: actions/checkout@v4
      - uses: MarkPhamm/quickdbd-cli@v0.6.0
        with:
          path: erd/                  # schema file(s) or folder(s)
          output: site/index.html
```

**What it does.** On every run, it:

1. installs qdbd from PyPI (and, with `dbt-manifest`, runs `qdbd import dbt`);
2. runs `qdbd check` and fails the job on errors (or warnings, with `strict: true`), annotating each problem on its line in the pull request;
3. builds the HTML diagram and uploads it as the **erd** artifact.

On pull requests it also:

4. fetches the base branch and runs `qdbd diff --base origin/<base>`;
5. builds the diagram with `--diff-base`, so changes are highlighted;
6. posts **one** comment with the markdown diff, and updates that same comment on later pushes.

## 7.2 Inputs { #inputs }

| Input | Default | |
|---|---|---|
| `path` | `erd/` | schema files or folders, space-separated; with `dbt-manifest`, where the import writes |
| `dbt-manifest` | | dbt `manifest.json` or `target/`: generate the schema with `qdbd import dbt` first |
| `dbt-args` | | extra import options, e.g. `--infer-fks --no-sources` |
| `dbt-check` | `false` | with `dbt-manifest`: don't regenerate; fail if the committed files are out of date |
| `output` | `erd/index.html` | where to write the HTML |
| `site` | | a folder for one diagram per `path` entry plus an index ([several diagrams](#several-diagrams)); replaces `output` |
| `check` | `true` | fail on schema errors |
| `strict` | `false` | also fail on QuickDBD-compatibility warnings |
| `comment` | `true` | post the diff comment on pull requests |
| `select` | | [selector](selectors.md) for the diagram |
| `upload-artifact` | `true` | upload the HTML (or the `site` folder) as `erd` |
| `qdbd-version` | `latest` | PyPI version to install |
| `python-version` | `3.12` | |
| `github-token` | `${{ github.token }}` | token for the comment |

## 7.3 Outputs { #outputs }

| Output | |
|---|---|
| `html` | path of the built page (with `site`, its `index.html`) |
| `changed` | `"true"` when the pull request changes the schema |
| `diff-file` | markdown diff (pull requests) |

## 7.4 Publishing to GitHub Pages { #publishing-to-github-pages }

!!! warning "A Pages site is public unless you restrict it"
    Anyone can open a GitHub Pages site, unless it's published from a private or internal repository of an organisation on GitHub Enterprise Cloud with [access control](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site) turned on. Publish a client's schema only where their agreement allows it. Publishing means you accept the [disclaimer](sharing.md#disclaimer).

Upload `output`'s folder with `actions/upload-pages-artifact` and deploy it with `actions/deploy-pages` on pushes to your main branch. [5.6 Step 4: Automate in CI](example/ci.md#publish-the-diagram) has the full workflow.

### Several diagrams { #several-diagrams }

When each folder is its own diagram (say `docs/erd/sales/` and `docs/erd/hr/`), set `site` instead of `output`. The action then builds `site/sales.html`, `site/hr.html` and an `index.html` linking them, with [`qdbd build --site`](cli.md#build). Each folder is checked and diffed on its own, so two diagrams can share table names, and the pull request comment has a section per folder:

```yaml
- uses: MarkPhamm/quickdbd-cli@v0.6.0
  with:
    path: docs/erd/*/
    site: site/
```

The glob is expanded by the shell, and folders with no schema files are skipped. Deploy `site/` to Pages as above.

## 7.5 With dbt { #with-dbt }

Run your dbt build first, then point the action at the manifest:

```yaml
- uses: MarkPhamm/quickdbd-cli@v0.6.0
  with:
    dbt-manifest: target/
    dbt-args: --infer-fks
    path: erd/
```

Commit `erd/` so pull requests have a base to diff against. Walkthrough: [5.6 Step 4: Automate in CI](example/ci.md).

For a hand-drawn ERD linked to the yml with `# @dbt:` (no manifest), [qdbd-dbt-demo](https://github.com/MarkPhamm/qdbd-dbt-demo) is a working setup: `qdbd check --strict` fails a pull request on drift, and each branch publishes its own diagram to Pages.

## 7.6 GitLab CI and others { #not-on-github }

The action only wraps the CLI, so any CI can run the same commands. On GitLab, this checks the schema on every pipeline that changes it, keeps the diagram as a job artifact, and publishes it to GitLab Pages from the default branch:

```yaml title=".gitlab-ci.yml"
.qdbd:
  image: python:3.12-slim
  before_script: [pip install quickdbd-cli]
  rules:
    - changes: [erd/**/*]

erd:
  extends: .qdbd
  script:
    - qdbd check --strict erd/
    - qdbd build erd/ -o public/index.html
  artifacts:
    paths: [public/]

pages:
  extends: .qdbd
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      changes: [erd/**/*]
  script:
    - qdbd build erd/ -o public/index.html
  artifacts:
    paths: [public/]
```

GitLab publishes the `public/` folder of a job named `pages`.

!!! warning "A Pages site may be public"
    Who can open a GitLab Pages site depends on the project's visibility and its Pages access control setting. Publish a client's schema only where their agreement allows it. Publishing means you accept the [disclaimer](sharing.md#disclaimer).

For one diagram per folder, as in [several diagrams](#several-diagrams), use `--each` and `--site`:

```yaml
    - qdbd check --strict --each docs/erd/*/
    - qdbd build docs/erd/*/ --site public/
```

## 7.7 pre-commit { #pre-commit }

To check schema files before every commit, add the [pre-commit](https://pre-commit.com) hook:

```yaml
repos:
  - repo: https://github.com/MarkPhamm/quickdbd-cli
    rev: v0.6.0
    hooks:
      - id: qdbd-check
        files: ^erd/.*\.(txt|dbml)$
```
