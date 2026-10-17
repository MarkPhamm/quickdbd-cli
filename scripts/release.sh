#!/usr/bin/env bash
# Build and upload the current version to PyPI using credentials from .env,
# then tag and create the GitHub release.
# Usage: bump `version` in pyproject.toml and src/quickdbd_cli/__init__.py, commit, then run scripts/release.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "error: .env with TWINE_USERNAME/TWINE_PASSWORD not found" >&2; exit 1; }
set -a; . ./.env; set +a

version=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "error: uncommitted changes" >&2; exit 1; }

rm -rf dist
python3 -m pip install -q --upgrade build twine
python3 -m build
python3 -m twine check dist/*
python3 -m twine upload --non-interactive dist/*

git tag -a "v$version" -m "qdbd v$version"
git push origin "v$version"
gh release create "v$version" dist/* --title "qdbd v$version" --generate-notes
echo "Released v$version: https://pypi.org/project/quickdbd-cli/$version/"
