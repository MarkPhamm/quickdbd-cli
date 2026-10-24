"""Install snippets in the README and docs pin the version being released."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
PIN = re.compile(r"quickdbd-cli@v(\d+\.\d+\.\d+)|quickdbd-cli==(\d+\.\d+\.\d+)|rev: v(\d+\.\d+\.\d+)")


def test_snippets_pin_the_current_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    files = [ROOT / "README.md", *(p for p in (ROOT / "docs").rglob("*.md") if "superpowers" not in p.parts)]
    stale = [
        f"{f.relative_to(ROOT)}: {m.group(0)}"
        for f in files
        for m in PIN.finditer(f.read_text(encoding="utf-8"))
        if version not in m.groups()
    ]
    assert not stale, f"bump these to {version}: {stale}"
