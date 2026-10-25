"""`qdbd mcp`: the MCP protocol in both eras (modern 2026-07-28 and the initialize-based ones), over stdio."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quickdbd_cli.agent import TOOLS, Workspace
from quickdbd_cli.mcp import LEGACY, MODERN, Server

SCHEMA = """customers
-
customer_id PK int
email string

orders
-
order_id PK int
customer_id int FK >- customers.customer_id
"""
META = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientCapabilities": {},
}


@pytest.fixture
def project(tmp_path):
    (tmp_path / "shop.txt").write_text(SCHEMA)
    (tmp_path / "notes.txt").write_text("not a schema")
    return tmp_path


@pytest.fixture
def server(project, monkeypatch):
    monkeypatch.chdir(project)
    return Server(Workspace(project))


def req(method, params=None, id_=1, modern=True):
    params = dict(params or {})
    if modern:
        params["_meta"] = {**META, **params.get("_meta", {})}
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}


def one(server, msg):
    out = server.handle(msg)
    assert len(out) == 1
    return out[0]


def validate(method, version, result):
    """The official SDK's schema for this result, when the SDK is installed."""
    methods = pytest.importorskip("mcp_types.methods")
    methods.validate_server_result(method, version, result)


# ------------------------------------------------------------------ modern era


def test_discover(server):
    r = one(server, req("server/discover"))["result"]
    assert r["resultType"] == "complete"
    assert r["supportedVersions"] == [MODERN]
    assert r["capabilities"] == {"tools": {}}
    assert r["ttlMs"] >= 0 and r["cacheScope"] in ("public", "private")
    assert r["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "qdbd"
    assert "join_path" in r["instructions"]
    validate("server/discover", MODERN, r)


def test_modern_tools_list_and_call(server):
    r = one(server, req("tools/list"))["result"]
    assert [t["name"] for t in r["tools"]] == [t.name for t in TOOLS]
    assert r["ttlMs"] >= 0 and r["cacheScope"]
    assert all(t["annotations"]["readOnlyHint"] for t in r["tools"])
    validate("tools/list", MODERN, r)
    r = one(server, req("tools/call", {"name": "join_path", "arguments": {"from": "orders", "to": "customers"}}))
    res = r["result"]
    assert res["isError"] is False and res["resultType"] == "complete"
    assert "JOIN customers ON customers.customer_id = orders.customer_id" in res["content"][0]["text"]
    validate("tools/call", MODERN, res)


def test_empty_lists_carry_cache_hints(server):
    for method in ("resources/list", "resources/templates/list", "prompts/list"):
        r = one(server, req(method))["result"]
        validate(method, MODERN, r)


def test_modern_errors(server):
    bad = one(server, req("tools/list", {"_meta": {"io.modelcontextprotocol/protocolVersion": "2025-11-25"}}))
    assert bad["error"]["code"] == -32022
    assert bad["error"]["data"]["requested"] == "2025-11-25" and MODERN in bad["error"]["data"]["supported"]
    no_caps = req("tools/list")
    del no_caps["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
    assert one(server, no_caps)["error"]["code"] == -32602
    assert one(server, req("ping"))["error"]["code"] == -32601  # removed in 2026-07-28
    assert one(server, req("nope/nope"))["error"]["code"] == -32601
    assert one(server, req("tools/call", {"name": "nope"}))["error"]["code"] == -32602


def test_tool_failures_are_results_the_agent_can_read(server):
    res = one(server, req("tools/call", {"name": "describe_tables", "arguments": {"tables": ["custmers"]}}))["result"]
    assert res["isError"] is True
    assert "Closest: customers" in res["content"][0]["text"]
    res = one(server, req("tools/call", {"name": "join_path", "arguments": {"from": "orders"}}))["result"]
    assert res["isError"] and "missing argument `to`" in res["content"][0]["text"]
    res = one(server, req("tools/call", {"name": "list_tables", "arguments": {"bogus": 1}}))["result"]
    assert res["isError"] and "unknown argument" in res["content"][0]["text"]


def test_subscriptions_listen_is_acknowledged_then_ends(server):
    out = server.handle(req("subscriptions/listen", {"notifications": {"toolsListChanged": True}}, id_=7))
    assert out[0]["method"] == "notifications/subscriptions/acknowledged"
    assert out[0]["params"]["_meta"]["io.modelcontextprotocol/subscriptionId"] == 7
    assert out[1]["id"] == 7 and out[1]["result"]["resultType"] == "complete"


def test_modern_answers_dont_change_after_an_initialize(server):
    before = one(server, req("tools/list"))
    one(server, req("initialize", {"protocolVersion": "2024-11-05"}, modern=False))
    assert one(server, req("tools/list")) == before


# ------------------------------------------------------------------ legacy era


@pytest.mark.parametrize("version", LEGACY)
def test_legacy_handshake_and_tools(project, monkeypatch, version):
    monkeypatch.chdir(project)
    s = Server(Workspace(project))
    init = one(s, req("initialize", {"protocolVersion": version, "capabilities": {}}, modern=False))["result"]
    assert init["protocolVersion"] == version
    assert init["serverInfo"]["name"] == "qdbd" and "resultType" not in init
    validate("initialize", version, init)
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) == []
    tools = one(s, req("tools/list", id_=2, modern=False))["result"]["tools"]
    assert ("annotations" in tools[0]) == (version >= "2025-03-26")
    assert ("title" in tools[0]) == (version >= "2025-06-18")
    validate("tools/list", version, {"tools": tools})
    call = {"name": "list_tables", "arguments": {}, "_meta": {"progressToken": 1}}  # legacy _meta is fine
    res = one(s, req("tools/call", call, id_=3, modern=False))["result"]
    assert "2 table(s)" in res["content"][0]["text"] and "resultType" not in res
    validate("tools/call", version, res)


def test_legacy_rules(server):
    assert one(server, req("ping", modern=False)) == {"jsonrpc": "2.0", "id": 1, "result": {}}  # before initialize too
    assert one(server, req("tools/list", modern=False))["error"]["code"] == -32602  # no initialize yet
    init = one(server, req("initialize", {"protocolVersion": "1999-01-01"}, modern=False))["result"]
    assert init["protocolVersion"] == LEGACY[0]


def test_batches_only_for_2025_03_26(server):
    batch = [req("ping", id_=1, modern=False), {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    assert server.handle(batch)[0]["error"]["code"] == -32600
    one(server, req("initialize", {"protocolVersion": "2025-03-26"}, modern=False))
    [answers] = server.handle(batch + [req("tools/list", id_=2, modern=False)])
    assert [a["id"] for a in answers] == [1, 2]
    assert server.handle([{"jsonrpc": "2.0", "method": "notifications/initialized"}]) == []
    assert server.handle([])[0]["error"]["code"] == -32600


def test_junk(server):
    assert server.handle({"jsonrpc": "2.0", "id": 5, "result": {}}) == []  # a stray response
    assert server.handle("hello")[0]["error"]["code"] == -32600
    assert one(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": []})["error"]["code"] == -32602


# ------------------------------------------------------------------ stdio


def run(args, lines, cwd, timeout=60):
    p = subprocess.run(
        [sys.executable, "-m", "quickdbd_cli", "mcp", *args],
        input=b"".join(json.dumps(m).encode() + b"\n" for m in lines) + b"not json\n\n",
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
    )
    return p


def test_stdout_carries_only_protocol_messages(project, monkeypatch):
    """Stray prints and child processes from a tool go to stderr, never the protocol stream."""
    from quickdbd_cli import agent

    plugin = project / "noisy.py"
    plugin.write_text(
        "import subprocess, sys\n"
        "from quickdbd_cli import agent\n"
        "orig = agent.list_tables\n"
        "def noisy(ws, args):\n"
        "    print('stray print')\n"
        "    subprocess.run([sys.executable, '-c', 'print(\"child output\")'])\n"
        "    return orig(ws, args)\n"
        "agent.TOOLS[1].run = noisy\n"
        "from quickdbd_cli.cli import main\n"
        "sys.exit(main(['mcp', 'shop.txt']))\n"
    )
    assert agent.TOOLS[1].name == "list_tables"
    msgs = [req("server/discover"), req("tools/call", {"name": "list_tables", "arguments": {}}, id_=2)]
    p = subprocess.run(
        [sys.executable, str(plugin)],
        input=b"".join(json.dumps(m).encode() + b"\n" for m in msgs) + b"not json\n",
        cwd=project,
        capture_output=True,
        timeout=60,
    )
    assert p.returncode == 0, p.stderr
    assert b"\r" not in p.stdout
    lines = p.stdout.decode().splitlines()
    replies = [json.loads(x) for x in lines]  # every line is one JSON-RPC message
    assert [r.get("id") for r in replies] == [1, 2, None]
    assert replies[2]["error"]["code"] == -32700
    assert b"stray print" in p.stderr and b"child output" in p.stderr


def test_cli_errors_before_serving(project):
    p = run(["missing.txt"], [], project)
    assert p.returncode == 2 and b"no such file" in p.stderr and p.stdout == b""


# ------------------------------------------------------------------ the official SDK as a client


@pytest.mark.parametrize("mode", ["auto", MODERN, "legacy"])
def test_official_sdk_client(project, mode):
    """The `mcp` SDK talks to `qdbd mcp` in each era; it validates every result with its own schemas."""
    mcp = pytest.importorskip("mcp")
    anyio = pytest.importorskip("anyio")

    async def go():
        params = mcp.StdioServerParameters(
            command=sys.executable, args=["-m", "quickdbd_cli", "mcp", "shop.txt"], cwd=str(project)
        )
        async with mcp.Client(params, mode=mode, read_timeout_seconds=60) as client:
            names = [t.name for t in (await client.list_tools()).tools]
            res = await client.call_tool("join_path", {"from": "orders", "to": "customers"})
            info = client.server_info if mode == "auto" else None
            return client.protocol_version, info, names, res

    version, info, names, res = anyio.run(go)
    assert names == [t.name for t in TOOLS]
    assert not res.is_error and "JOIN customers" in res.content[0].text
    assert version == (LEGACY[0] if mode == "legacy" else MODERN)
    if mode == "auto":  # probed with server/discover and stayed modern
        assert info is not None and info.name == "qdbd"


def test_package_runs_as_module():
    assert Path(__file__).parent.parent.joinpath("src", "quickdbd_cli", "__main__.py").exists()
