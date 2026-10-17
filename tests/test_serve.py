"""`qdbd serve` HTTP endpoints, driven without a browser."""

import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from quickdbd_cli import layout
from quickdbd_cli.project import Project, display_path
from quickdbd_cli.serve import make_server, poll_once

SCHEMA = """Customer
-
CustomerId PK int
Name string

Order
-
OrderId PK int
CustomerId int FK >- Customer.CustomerId
"""


@pytest.fixture
def srv(tmp_path):
    f = tmp_path / "shop.txt"
    f.write_text(SCHEMA)
    server, state = make_server(Project.open([f]), port=0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, state, f
    server.shutdown()
    server.server_close()


def call(base, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def bump_mtime(path):
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def test_page_and_state(srv):
    base, _, f = srv
    code, page = call(base, "/")
    assert code == 200 and b'id="side"' in page and b'"serve":true' in page
    code, st = call(base, "/state")
    assert code == 200
    assert [t["name"] for t in st["model"]["tables"]] == ["Customer", "Order"]
    assert st["files"] == [{"path": display_path(f), "text": SCHEMA, "mtime": st["files"][0]["mtime"]}]
    assert isinstance(st["files"][0]["mtime"], str)  # ns mtimes overflow JS numbers
    assert st["diagnostics"] == []


def test_initial_layout_written_to_sidecar(srv):
    _, state, f = srv
    side = layout.read_sidecar(f.with_name("shop.layout.json"))
    assert set(side) == {"Customer", "Order"}


def test_put_file_saves_and_returns_new_mtime(srv):
    base, _, f = srv
    _, st = call(base, "/state")
    path, mtime = st["files"][0]["path"], st["files"][0]["mtime"]
    new = SCHEMA + "\nProduct\n-\nProductId PK int\n"
    code, res = call(base, "/file", "PUT", {"path": path, "text": new, "mtime": mtime})
    assert code == 200 and res["mtime"] != mtime
    assert f.read_text() == new


def test_put_file_refuses_stale_write(srv):
    base, _, f = srv
    _, st = call(base, "/state")
    path, mtime = st["files"][0]["path"], st["files"][0]["mtime"]
    f.write_text(SCHEMA + "\n# edited elsewhere\n")
    bump_mtime(f)
    code, res = call(base, "/file", "PUT", {"path": path, "text": "clobber", "mtime": mtime})
    assert code == 409
    assert "# edited elsewhere" in res["text"]
    assert "# edited elsewhere" in f.read_text()  # disk untouched


def test_put_unknown_file(srv):
    base, _, _ = srv
    code, _ = call(base, "/file", "PUT", {"path": "nope.txt", "text": "x", "mtime": None})
    assert code == 404


def test_post_layout_updates_sidecar(srv):
    base, state, f = srv
    code, _ = call(base, "/layout", "POST", {"Customer": [1234, 567], "Unknown": [1, 1]})
    assert code == 200
    side = layout.read_sidecar(f.with_name("shop.layout.json"))
    assert side["Customer"] == (1234, 567)
    assert "Unknown" not in side
    _, st = call(base, "/state")
    assert st["positions"]["Customer"] == [1234, 567]


def test_external_edit_reloads_and_places_new_table(srv):
    base, state, f = srv
    _, before = call(base, "/state")
    f.write_text(SCHEMA + "\nLine\n-\nLineId PK int\nOrderId int FK >- Order.OrderId\n")
    bump_mtime(f)
    assert poll_once(state)
    _, after = call(base, "/state")
    assert after["version"] > before["version"]
    assert "Line" in after["positions"]
    # existing tables did not move
    for t in ("Customer", "Order"):
        assert after["positions"][t] == before["positions"][t]
    assert not poll_once(state)  # nothing changed since


def test_errors_keep_last_good_model(srv):
    base, state, f = srv
    f.write_text(SCHEMA + "\nBad\n-\nX int FK >- Nope.Id\n")
    bump_mtime(f)
    poll_once(state)
    _, st = call(base, "/state")
    assert [d["severity"] for d in st["diagnostics"]] == ["error"]
    assert "Invalid relationship, the table 'Nope' does not exist" in st["diagnostics"][0]["text"]
    assert [t["name"] for t in st["model"]["tables"]] == ["Customer", "Order"]


def test_events_stream_announces_versions(srv):
    base, state, f = srv
    got = []

    def listen():
        with urllib.request.urlopen(base + "/events", timeout=10) as r:
            for line in r:
                line = line.decode().strip()
                if line.startswith("data:"):
                    got.append(int(line[5:]))
                    if len(got) == 2:
                        return

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.3)
    f.write_text(SCHEMA + "\n# touch\n")
    bump_mtime(f)
    poll_once(state)
    t.join(timeout=10)
    assert len(got) == 2 and got[1] > got[0]
