#!/usr/bin/env bash
# Build and upload the current version to PyPI using credentials from .env,
# then tag and create the GitHub release, with the VS Code extension (.vsix) attached.
# Usage: bump `version` in pyproject.toml and src/quickdbd_cli/__init__.py, commit, then run
#   PATH="$PWD/.venv/bin:$PATH" scripts/release.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "error: .env with TWINE_USERNAME/TWINE_PASSWORD not found" >&2; exit 1; }
set -a; . ./.env; set +a

version=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "error: uncommitted changes" >&2; exit 1; }

rm -rf dist
# uv-created venvs have no pip; only install the tools when they're missing.
python3 -c "import build, twine" 2>/dev/null || {
  if command -v uv >/dev/null; then uv pip install -q --python "$(command -v python3)" build twine
  else python3 -m pip install -q --upgrade build twine; fi
}
python3 -m build
python3 -m twine check dist/*

# The extension is packaged before anything is uploaded, so a Node problem doesn't leave half a release.
node -e 'process.exit(+process.versions.node.split(".")[0] >= 20 ? 0 : 1)' 2>/dev/null || {
  echo "error: packaging the VS Code extension needs Node 20+ on PATH" >&2; exit 1; }
rm -f vscode/*.vsix
(cd vscode && npm ci --no-audit --no-fund && npm run -s package)
vsix=$(ls vscode/*.vsix)
python3 -m twine upload --non-interactive dist/*

git tag -a "v$version" -m "qdbd v$version"
git push origin "v$version"
gh release create "v$version" dist/* "$vsix" --title "qdbd v$version" --generate-notes
echo "Released v$version: https://pypi.org/project/quickdbd-cli/$version/"
