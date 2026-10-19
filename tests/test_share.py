"""`qdbd share`, with `gh api` faked (no network)."""

import json
import subprocess

import pytest

from quickdbd_cli import share
from quickdbd_cli.cli import main

SCHEMA = "Customer\n-\nId PK int\n\nOrder\n-\nId PK int\nCustomerId int FK >- Customer.Id\n"


class FakeGh:
    def __init__(self):
        self.calls = []
        self.gists = {}
        self.fail = None

    def __call__(self, cmd, input=None, **kw):
        assert cmd[:3] == ["gh", "api", "--method"] and cmd[-2:] == ["--input", "-"]
        method, endpoint, payload = cmd[3], cmd[4], json.loads(input)
        self.calls.append((method, endpoint, payload))
        if self.fail:
            return subprocess.CompletedProcess(cmd, 1, "", self.fail)
        if method == "POST":
            gid = f"g{len(self.gists) + 1}"
            self.gists[gid] = payload
            body = {"id": gid, "html_url": f"https://gist.github.com/me/{gid}", "public": payload["public"]}
        else:
            gid = endpoint.rsplit("/", 1)[1]
            if gid not in self.gists:
                return subprocess.CompletedProcess(cmd, 1, "", "gh: Not Found (HTTP 404)")
            self.gists[gid]["files"].update(payload["files"])
            body = {"id": gid, "html_url": f"https://gist.github.com/me/{gid}", "public": self.gists[gid]["public"]}
        body["owner"] = {"login": "me"}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(body), "")


@pytest.fixture
def gh(monkeypatch, tmp_path):
    fake = FakeGh()
    monkeypatch.setattr(share.subprocess, "run", fake)
    monkeypatch.setenv("QDBD_CACHE_DIR", str(tmp_path / "cache"))
    return fake


@pytest.fixture
def schema(tmp_path):
    f = tmp_path / "shop.txt"
    f.write_text(SCHEMA)
    return f


def test_share_creates_a_secret_gist_and_prints_links(gh, schema, capsys):
    assert main(["share", str(schema)]) == 0
    out = capsys.readouterr().out
    method, endpoint, payload = gh.calls[0]
    assert (method, endpoint, payload["public"]) == ("POST", "/gists", False)
    assert list(payload["files"]) == ["shop.html"]
    assert payload["files"]["shop.html"]["content"].startswith("<!doctype html>")
    assert "Shared 2 tables (secret gist https://gist.github.com/me/g1)" in out
    assert "Link: https://gist.githack.com/me/g1/raw/shop.html" in out
    assert "https://gistpreview.github.io/?g1" in out


def test_sharing_again_updates_the_same_gist(gh, schema, capsys):
    main(["share", str(schema)])
    schema.write_text(SCHEMA + "\nProduct\n-\nId PK int\n")
    assert main(["share", str(schema)]) == 0
    assert [c[0] for c in gh.calls] == ["POST", "PATCH"]
    assert gh.calls[1][1] == "/gists/g1"
    assert "Product" in gh.gists["g1"]["files"]["shop.html"]["content"]
    assert "Updated 3 tables" in capsys.readouterr().out


def test_new_and_selection_make_separate_gists(gh, schema):
    main(["share", str(schema)])
    main(["share", str(schema), "--new"])
    main(["share", str(schema), "-s", "Order+"])
    assert [c[0] for c in gh.calls] == ["POST", "POST", "POST"]
    main(["share", str(schema), "-s", "Order+"])
    assert gh.calls[-1][:2] == ("PATCH", "/gists/g3")


def test_deleted_gist_is_recreated(gh, schema):
    main(["share", str(schema)])
    gh.gists.clear()
    assert main(["share", str(schema)]) == 0
    assert [c[0] for c in gh.calls] == ["POST", "PATCH", "POST"]


def test_public_flag(gh, schema, capsys):
    main(["share", str(schema), "--public"])
    assert gh.calls[0][2]["public"] is True
    assert "(public gist" in capsys.readouterr().out


def test_errors(gh, schema, capsys, monkeypatch):
    gh.fail = "To get started with GitHub CLI, please run:  gh auth login"
    assert main(["share", str(schema)]) == 2
    assert "run gh auth login" in capsys.readouterr().err

    def missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(share.subprocess, "run", missing)
    assert main(["share", str(schema)]) == 2
    assert "needs the GitHub CLI" in capsys.readouterr().err


def test_schema_errors_stop_before_uploading(gh, tmp_path):
    f = tmp_path / "bad.txt"
    f.write_text("A\n-\nId int FK >- Nope.Id\n")
    assert main(["share", str(f)]) == 1
    assert gh.calls == []
