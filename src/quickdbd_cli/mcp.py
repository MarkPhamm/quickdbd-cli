"""`qdbd mcp`: a Model Context Protocol server over stdio, standard library only.

It speaks both protocol eras:
- modern (2026-07-28): stateless; every request carries its version and client capabilities in
  `params._meta`, and `server/discover` describes the server;
- legacy (2025-11-25 and earlier): an `initialize` handshake picks the version for the rest of the process.

A request is modern iff its `_meta` holds `io.modelcontextprotocol/protocolVersion`. The tools live in agent.py.
Stdout carries only protocol messages: `isolate_stdio` moves everything else (stray prints, child processes) to stderr.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import traceback
from typing import BinaryIO

from . import __version__
from .agent import INSTRUCTIONS, TOOLS, Result, Tool, ToolError, Workspace

MODERN = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SUPPORTED = [MODERN, *LEGACY]
PV = "io.modelcontextprotocol/protocolVersion"
CAPS = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO = "io.modelcontextprotocol/serverInfo"
SUB_ID = "io.modelcontextprotocol/subscriptionId"
CACHE = {"ttlMs": 3_600_000, "cacheScope": "public"}  # the tool list never changes while the process runs
INFO = {"name": "qdbd", "version": __version__}
ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
EMPTY_LISTS = {
    "resources/list": "resources",
    "resources/templates/list": "resourceTemplates",
    "prompts/list": "prompts",
}


def _error(id_, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def _ok(id_, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


class _Log:
    """Keeps stderr short: a client may never read it, and a full pipe would stall the server."""

    def __init__(self, stream=None) -> None:
        self.stream = stream
        self.seen: set[str] = set()
        self.debug = bool(os.environ.get("QDBD_MCP_DEBUG"))

    def line(self, text: str) -> None:
        try:
            print(f"qdbd mcp: {text}", file=self.stream or sys.stderr, flush=True)
        except (OSError, ValueError):
            pass

    def failure(self, tool: str, e: BaseException) -> None:
        self.line(f"{tool} failed: {type(e).__name__}: {e}")
        if self.debug or type(e).__name__ not in self.seen:
            self.seen.add(type(e).__name__)
            self.line("".join(traceback.format_exception(e)).rstrip())


def _check_args(tool: Tool, args: dict) -> None:
    """The parts of JSON Schema the tool definitions use; a mismatch is a tool error the agent can fix."""
    props = tool.properties
    for k in tool.required:
        if args.get(k) in (None, ""):
            raise ToolError(f"missing argument `{k}`")
    for k, v in args.items():
        if k not in props:
            raise ToolError(f"unknown argument `{k}` (expected: {', '.join(props) or 'none'})")
        spec = props[k]
        kind = spec.get("type")
        ok = {
            "string": isinstance(v, str),
            "boolean": isinstance(v, bool),
            "integer": isinstance(v, int) and not isinstance(v, bool),
            "array": isinstance(v, list) and all(isinstance(x, str) for x in v),
        }.get(kind, True)
        if not ok:
            raise ToolError(f"`{k}` must be a {'list of strings' if kind == 'array' else kind}")
        if "enum" in spec and v not in spec["enum"]:
            raise ToolError(f"`{k}` must be one of {', '.join(spec['enum'])}")
        if kind == "string" and len(v) > spec.get("maxLength", 10**9):
            raise ToolError(f"`{k}` is too long")
        if kind == "array" and len(v) > spec.get("maxItems", 10**9):
            raise ToolError(f"`{k}` has too many items (at most {spec['maxItems']})")
        if kind == "integer" and not spec.get("minimum", v) <= v <= spec.get("maximum", v):
            raise ToolError(f"`{k}` must be between {spec['minimum']} and {spec['maximum']}")


class Server:
    """Turns one incoming JSON-RPC message into the messages to send back (often one, none for notifications)."""

    def __init__(self, workspace: Workspace, log: _Log | None = None) -> None:
        self.ws = workspace
        self.log = log or _Log()
        self.legacy: str | None = None  # the version `initialize` negotiated, if any

    # ------------------------------------------------------------------ dispatch

    def handle(self, msg) -> list:
        if isinstance(msg, list):
            if self.legacy == "2025-03-26" and msg:  # the only revision with JSON-RPC batches
                out = [m for item in msg for m in self.handle(item) if not isinstance(item, list)]
                return [out] if out else []
            return [_error(None, -32600, "Invalid Request: batches are not supported")]
        if not isinstance(msg, dict):
            return [_error(None, -32600, "Invalid Request")]
        method, id_ = msg.get("method"), msg.get("id")
        if method is None:
            return []  # a response from the client: this server never asks anything
        is_request = "id" in msg
        if msg.get("jsonrpc") != "2.0" or not isinstance(method, str) or (is_request and id_ is None):
            return [_error(id_, -32600, "Invalid Request")] if is_request else []
        params = msg.get("params", {})
        if not isinstance(params, dict):
            return [_error(id_, -32602, "params must be an object")] if is_request else []
        if not is_request:
            return []  # notifications: initialized, cancelled (requests run one at a time), ...
        meta = params.get("_meta")
        if isinstance(meta, dict) and PV in meta:
            return self._modern(id_, method, params, meta)
        return self._legacy(id_, method, params)

    def _modern(self, id_, method: str, params: dict, meta: dict) -> list:
        version = meta[PV]
        if version != MODERN:
            data = {"supported": SUPPORTED, "requested": version}
            return [_error(id_, -32022, "Unsupported protocol version", data)]
        if not isinstance(meta.get(CAPS), dict):
            return [_error(id_, -32602, f"missing _meta {CAPS}")]

        def done(result: dict, cached: bool = False) -> list:
            meta_out = {**result.pop("_meta", {}), SERVER_INFO: INFO}
            return [_ok(id_, {"resultType": "complete", **result, **(CACHE if cached else {}), "_meta": meta_out})]

        if method == "server/discover":
            caps = {"tools": {}}
            return done({"supportedVersions": [MODERN], "capabilities": caps, "instructions": INSTRUCTIONS}, True)
        if method == "tools/list":
            return done({"tools": self._tools(MODERN)}, True)
        if method in EMPTY_LISTS:
            return done({EMPTY_LISTS[method]: []}, True)
        if method == "tools/call":
            res = self._call(params)
            return [_error(id_, -32602, res)] if isinstance(res, str) else done(res)
        if method == "subscriptions/listen":  # nothing to notify about: acknowledge, then end it
            ack = {"_meta": {SUB_ID: id_}, "notifications": {}}
            note = {"jsonrpc": "2.0", "method": "notifications/subscriptions/acknowledged", "params": ack}
            return [note, *done({"_meta": {SUB_ID: id_}})]
        return [_error(id_, -32601, f"Method not found: {method}")]

    def _legacy(self, id_, method: str, params: dict) -> list:
        if method == "ping":
            return [_ok(id_, {})]
        if method == "initialize":
            asked = params.get("protocolVersion")
            self.legacy = asked if asked in LEGACY else LEGACY[0]
            result = {
                "protocolVersion": self.legacy,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": INFO,
                "instructions": INSTRUCTIONS,
            }
            return [_ok(id_, result)]
        if self.legacy is None:
            hint = f"send initialize first, or (protocol {MODERN}) put {PV} and {CAPS} in params._meta"
            return [_error(id_, -32602, f"Invalid params: {hint}")]
        if method == "tools/list":
            return [_ok(id_, {"tools": self._tools(self.legacy)})]
        if method in EMPTY_LISTS:
            return [_ok(id_, {EMPTY_LISTS[method]: []})]
        if method == "tools/call":
            res = self._call(params)
            return [_error(id_, -32602, res)] if isinstance(res, str) else [_ok(id_, res)]
        return [_error(id_, -32601, f"Method not found: {method}")]

    # ------------------------------------------------------------------ tools

    def _tools(self, version: str) -> list[dict]:
        out = []
        for t in TOOLS:
            d = {"name": t.name, "description": t.description, "inputSchema": t.input_schema()}
            if version >= "2025-06-18":
                d["title"] = t.title
            if version >= "2025-03-26":
                d["annotations"] = {"title": t.title, **ANNOTATIONS}
            out.append(d)
        return out

    def _call(self, params: dict) -> dict | str:
        """A tools/call result, or an error message for a protocol error (unknown tool, malformed call)."""
        name, args = params.get("name"), params.get("arguments", {})
        tool = next((t for t in TOOLS if t.name == name), None)
        if tool is None:
            return f"Unknown tool: {name}"
        if not isinstance(args, dict):
            return "arguments must be an object"
        try:
            _check_args(tool, args)
            res: Result = tool.run(self.ws, args)
        except ToolError as e:
            res = Result(str(e), error=True)
        except Exception as e:
            self.log.failure(tool.name, e)
            res = Result(f"internal error: {type(e).__name__}: {e}", error=True)
        content = [{"type": "text", "text": res.text}]
        if res.image is not None:
            content.append(
                {"type": "image", "data": base64.b64encode(res.image).decode("ascii"), "mimeType": "image/png"}
            )
        return {"content": content, "isError": res.error}


# --------------------------------------------------------------------------- stdio


def isolate_stdio() -> tuple[BinaryIO, BinaryIO]:
    """Private copies of stdin/stdout for the protocol; fds 0/1 become devnull/stderr for everything else."""
    sys.stdout.flush()
    if os.name == "nt":
        fds = []
        for fd in (0, 1):
            new = os.dup(fd)
            os.set_inheritable(new, False)
            fds.append(new)
        wire_in, wire_out = fds
    else:
        import fcntl

        wire_in = fcntl.fcntl(0, fcntl.F_DUPFD_CLOEXEC, 3)
        wire_out = fcntl.fcntl(1, fcntl.F_DUPFD_CLOEXEC, 3)
    try:
        os.dup2(2, 1)
    except OSError:  # no stderr: send stray output nowhere
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, 1)
        os.close(null)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    if os.name == "nt":  # child processes inherit the Win32 handles, which dup2 doesn't touch
        import ctypes
        import msvcrt

        k32 = ctypes.windll.kernel32
        k32.SetStdHandle(-11, msvcrt.get_osfhandle(1))
        k32.SetStdHandle(-10, msvcrt.get_osfhandle(0))
    sys.stdout = sys.stderr
    return os.fdopen(wire_in, "rb"), os.fdopen(wire_out, "wb")


def serve(server: Server, rfile: BinaryIO, wfile: BinaryIO) -> int:
    """One JSON-RPC message per line in, one per line out, until stdin closes."""

    def send(m) -> None:
        wfile.write(json.dumps(m, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n")
        wfile.flush()

    try:
        for raw in rfile:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                send(_error(None, -32700, "Parse error"))
                continue
            for m in server.handle(msg):
                send(m)
    except (BrokenPipeError, ConnectionResetError, KeyboardInterrupt):
        pass
    return 0
