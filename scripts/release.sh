#!/usr/bin/env bash
# Build and upload the current version to PyPI using credentials from .env,
# then tag and create the GitHub release, with the VS Code extension (.vsix) attached.
# With OVSX_PAT in .env, the extension also goes to Open VSX (Cursor, Windsurf, VSCodium) when its version is new.
# The VS Code Marketplace is published by .github/workflows/publish-vscode.yml (Trusted Publishing); the script
# says when a run is due.
# Usage: bump `version` in pyproject.toml and src/quickdbd_cli/__init__.py, commit, then run
#   PATH="$PWD/.venv/bin:$PATH" scripts/release.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "error: .env with TWINE_USERNAME/TWINE_PASSWORD not found" >&2; exit 1; }
set -a; . ./.env; set +a

version=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "error: uncommitted changes" >&2; exit 1; }
# The sdist takes whole folders, so an untracked file in one would ship (examples/ leaked one in 0.1.18).
untracked=$(git ls-files --others --exclude-standard -- src tests examples scripts)
[ -z "$untracked" ] || { echo "error: untracked files would ship in the sdist:" >&2; echo "$untracked" >&2; exit 1; }

rm -rf dist
# uv-created venvs have no pip; only install the tools when they're missing.
python3 -c "import build, twine" 2>/dev/null || {
  if command -v uv >/dev/null; then uv pip install -q --python "$(command -v python3)" build twine
  else python3 -m pip install -q --upgrade build twine; fi
}
python3 -m build
python3 -m twine check dist/*

# The extension is packaged before anything is uploaded, so a Node problem doesn't leave half a release.
node -e 'process.exit(+process.versions.node.split(".")[0] >= 22 ? 0 : 1)' 2>/dev/null || {
  echo "error: packaging the VS Code extension needs Node 22+ on PATH" >&2; exit 1; }
rm -f vscode/*.vsix
(cd vscode && npm ci --no-audit --no-fund && npm run -s package)
vsix=$(ls vscode/*.vsix)
python3 -m twine upload --non-interactive dist/*

git tag -a "v$version" -m "qdbd v$version"
git push origin "v$version"
gh release create "v$version" dist/* "$vsix" --title "qdbd v$version" --generate-notes
echo "Released v$version: https://pypi.org/project/quickdbd-cli/$version/"

ext_version=$(node -p 'require("./vscode/package.json").version')
if [ -n "${OVSX_PAT:-}" ]; then
  vscode/node_modules/.bin/ovsx publish "$vsix" -p "$OVSX_PAT" --skip-duplicate
else
  echo "note: OVSX_PAT isn't set in .env, so the extension wasn't published to Open VSX"
fi
on_marketplace=$(curl -s -X POST https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery \
  -H "Content-Type: application/json" -H "Accept: application/json;api-version=7.2-preview.1" \
  -d '{"filters":[{"criteria":[{"filterType":7,"value":"MarkPhamm.quickdbd"}]}],"flags":1}' |
  python3 -c 'import json,sys; e=json.load(sys.stdin)["results"][0]["extensions"]; print(e[0]["versions"][0]["version"] if e else "")' ||
  true)
if [ "$on_marketplace" != "$ext_version" ]; then
  echo "action: publish extension $ext_version to the VS Code Marketplace: gh workflow run publish-vscode.yml"
fi
