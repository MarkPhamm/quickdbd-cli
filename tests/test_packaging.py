"""What the source distribution ships: only the project's own files, never the extension's node_modules or the
VS Code download its integration tests leave in vscode/.vscode-test."""

import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_DIRS = ("src/", "tests/", "examples/", "scripts/")
ALLOWED_FILES = {"README.md", "LICENSE", "NOTICE", "pyproject.toml", "PKG-INFO", ".gitignore"}


def _build_sdist(out: Path) -> Path:
    if shutil.which("uv"):
        cmd = ["uv", "build", "--sdist", "--out-dir", str(out), str(ROOT)]
    else:
        pytest.importorskip("build")
        cmd = [sys.executable, "-m", "build", "--sdist", "--outdir", str(out), str(ROOT)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"sdist build unavailable: {r.stderr.strip().splitlines()[-1:]}")
    return next(out.glob("*.tar.gz"))


def test_sdist_contains_only_expected_paths(tmp_path):
    # Built from the working tree, as scripts/release.sh does: ignored files there are what leaked before.
    sdist = _build_sdist(tmp_path)
    with tarfile.open(sdist) as tar:
        names = [n.split("/", 1)[1] for n in tar.getnames() if "/" in n]
    files = [n for n in names if not n.endswith("/")]
    unexpected = [n for n in files if not (n.startswith(ALLOWED_DIRS) or n in ALLOWED_FILES)]
    assert unexpected == []
    assert not [n for n in files if "node_modules" in n or ".vscode-test" in n]
