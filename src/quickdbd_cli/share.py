"""`qdbd share`: publish the built page as a GitHub gist and return a link to view it.

Uses the GitHub CLI (``gh api``), so it inherits the user's login. Gists are secret (unlisted) unless
``public``. The gist made for each input/selection is remembered in the user's cache directory, so
sharing again updates the same gist and the link stays the same. The VS Code extension does the same
without gh (vscode/src/gist.ts) and shares the cache: keep the two in step.

Off unless ``QDBD_ALLOW_SHARE`` is set: a gist puts the schema outside the organisation's control, which a
client's data agreements may not allow. The extension's own switch is the ``quickdbd.allowSharing`` setting.
Even then, every share shows ``DISCLAIMER`` and asks first; the extension's dialog (export.ts) says the same.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ALLOW_ENV = "QDBD_ALLOW_SHARE"
DISCLAIMER = """\
Before you share: this uploads the diagram (every table and column name, type, key, relationship
and comment) to a GitHub gist. Anyone with the link can open it, and copies can outlive the gist.
By sharing, you confirm that you have the right to publish this schema, that your organisation's
policies and any client agreements allow it, and that qdbd's authors are not liable for any
disclosure. Full disclaimer: https://qdbd.dev/sharing/#disclaimer"""


class ShareError(Exception):
    pass


def allowed() -> bool:
    return os.environ.get(ALLOW_ENV, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Shared:
    link: str  # gistpreview: renders the gist's HTML, keeps the #view part of the URL
    alt_link: str  # githack: serves the raw file as text/html (after a one-click confirmation page)
    gist_url: str
    public: bool
    updated: bool


def share_key(paths: list[str], select: str = "") -> str:
    return "|".join(sorted(str(Path(p).resolve()) for p in paths)) + "#" + select


def cache_file() -> Path:
    if os.environ.get("QDBD_CACHE_DIR"):
        base = Path(os.environ["QDBD_CACHE_DIR"])
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "qdbd"
    return base / "shares.json"


def _load() -> dict:
    try:
        return json.loads(cache_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save(data: dict) -> None:
    f = cache_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gh(method: str, endpoint: str, payload: dict) -> dict:
    try:
        r = subprocess.run(
            ["gh", "api", "--method", method, endpoint, "--input", "-"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        raise ShareError(
            "qdbd share needs the GitHub CLI: install it (brew install gh), then run gh auth login"
        ) from None
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if "auth login" in msg or "not logged" in msg.lower():
            raise ShareError("not logged in to GitHub: run gh auth login")
        raise ShareError(f"gh api {method} {endpoint} failed: {msg}")
    return json.loads(r.stdout)


def _filename(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-.") or "diagram"
    return f"{slug}.html"


def publish(page: str, title: str, key: str, public: bool = False, new: bool = False) -> Shared:
    cache = _load()
    entry = None if new else cache.get(key)
    desc = f"qdbd ERD: {title}"
    gist = None
    if entry:
        try:
            gist = _gh(
                "PATCH", f"/gists/{entry['id']}", {"description": desc, "files": {entry["file"]: {"content": page}}}
            )
        except ShareError as e:
            if "404" not in str(e) and "Not Found" not in str(e):
                raise
            entry = None  # the gist was deleted: make a new one
    updated = gist is not None
    fname = entry["file"] if entry else _filename(title)
    if gist is None:
        gist = _gh("POST", "/gists", {"description": desc, "public": public, "files": {fname: {"content": page}}})
    owner = (gist.get("owner") or {}).get("login") or ""
    cache[key] = {"id": gist["id"], "owner": owner, "file": fname}
    _save(cache)
    return Shared(
        link=f"https://gistpreview.github.io/?{gist['id']}",
        alt_link=f"https://gist.githack.com/{owner}/{gist['id']}/raw/{fname}",
        gist_url=gist.get("html_url", ""),
        public=bool(gist.get("public")),
        updated=updated,
    )
