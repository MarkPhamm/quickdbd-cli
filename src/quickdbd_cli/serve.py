"""`qdbd serve`: local live editor.

Watches the schema files (mtime polling), recompiles on change and pushes a reload event to the
page over Server-Sent Events. Dragged table positions are saved to the layout sidecar; the
browser editor pane writes the .txt files, refusing to overwrite a file changed on disk since
the browser last loaded it. With ``read_only`` the page is the plain viewer plus live reload, and
the server never writes anything.
"""

from __future__ import annotations

import errno
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import layout
from .html import render_page
from .project import Project, discover, display_path


class State:
    def __init__(self, project: Project, read_only: bool = False):
        self.project = project
        self.read_only = read_only  # never write to disk: no editor saves, no layout file
        self.lock = threading.Condition()
        self.version = 0
        self.model: dict = {"style": {}, "tables": [], "rels": [], "zoom": None, "position": None}
        self.positions: dict = {}
        self.diagnostics: list[dict] = []
        self.files: list[Path] = []
        # mtimes are strings: nanosecond integers exceed JavaScript's safe integer range.
        self.mtimes: dict[str, str] = {}
        self.reload(initial=True)

    def _scan(self) -> dict[str, str]:
        self.files = discover(self.project.inputs)
        self.project.files = self.files
        return {display_path(f): str(f.stat().st_mtime_ns) for f in self.files}

    def reload(self, initial: bool = False) -> None:
        mtimes = self._scan()
        schema = self.project.compile()
        diags = [
            {"path": d.path, "line": d.line, "message": d.message, "severity": d.severity, "text": d.format()}
            for d in schema.diagnostics
        ]
        with self.lock:
            self.mtimes = mtimes
            self.diagnostics = diags
            if not schema.errors:
                from .measure import model_json

                model = model_json(schema)
                base = layout.read_sidecar(self.project.sidecar)
                current = {
                    t["name"]: tuple(self.positions[t["id"]]) for t in self.model["tables"] if t["id"] in self.positions
                }
                base.update(current)
                pos = layout.resolve_positions(model, base, schema.layout)
                self.model = model
                self.positions = {k: [v[0], v[1]] for k, v in pos.items()}
                if not self.read_only:
                    self.project.save_positions(model, self.positions)
            self.version += 1
            self.lock.notify_all()
        if not initial:
            n = len(schema.errors)
            print(f"[qdbd] reloaded: {len(self.model['tables'])} tables" + (f", {n} error(s)" if n else ""), flush=True)

    def changed(self) -> bool:
        try:
            return self._scan() != self.mtimes
        except FileNotFoundError:
            return True

    def snapshot(self) -> dict:
        with self.lock:
            if self.read_only:  # the model only: no file text, no diagnostics
                return {"version": self.version, "model": self.model, "positions": self.positions}
            files = []
            for f in self.files:
                p = display_path(f)
                try:
                    text = f.read_text(encoding="utf-8")
                except FileNotFoundError:
                    continue
                files.append({"path": p, "text": text, "mtime": self.mtimes.get(p)})
            return {
                "version": self.version,
                "model": self.model,
                "positions": self.positions,
                "diagnostics": self.diagnostics,
                "files": files,
            }

    def save_layout(self, body: dict) -> None:
        with self.lock:
            by_name = {t["name"]: t["id"] for t in self.model["tables"]}
            for name, xy in body.items():
                if name in by_name:
                    self.positions[by_name[name]] = [int(xy[0]), int(xy[1])]
            self.project.save_positions(self.model, self.positions)

    def write_file(self, path: str, text: str, base_mtime: str | None) -> tuple[int, dict]:
        target = next((f for f in self.files if display_path(f) == path), None)
        if target is None:
            return 404, {"error": "unknown file"}
        current = str(target.stat().st_mtime_ns)
        if base_mtime is not None and current != str(base_mtime):
            return 409, {"error": "changed on disk", "text": target.read_text(encoding="utf-8"), "mtime": current}
        target.write_text(text, encoding="utf-8")
        return 200, {"mtime": str(target.stat().st_mtime_ns)}


def _handler(state: State, title: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self) -> None:
            if self.path == "/":
                with state.lock:
                    if state.read_only:
                        page = render_page(state.model, state.positions, title, live=True)
                    else:
                        page = render_page(state.model, state.positions, title, serve=True)
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif self.path == "/state":
                self._json(200, state.snapshot())
            elif self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seen = -1
                try:
                    while True:
                        with state.lock:
                            state.lock.wait_for(lambda s=seen: state.version != s, timeout=15)
                            v = state.version
                        msg = f"data: {v}\n\n" if v != seen else ": ping\n\n"
                        seen = v
                        self.wfile.write(msg.encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
            elif self.path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if state.read_only:
                self._json(403, {"error": "read-only"})
            elif self.path == "/layout":
                state.save_layout(self._body())
                self._json(200, {"ok": True})
            else:
                self._send(404, b"not found", "text/plain")

        def do_PUT(self) -> None:
            if state.read_only:
                self._json(403, {"error": "read-only"})
            elif self.path == "/file":
                b = self._body()
                code, obj = state.write_file(b.get("path", ""), b.get("text", ""), b.get("mtime"))
                self._json(code, obj)
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


class PortInUse(OSError):
    pass


def make_server(
    project: Project, port: int = 8765, read_only: bool = False, tries: int = 1
) -> tuple[ThreadingHTTPServer, State]:
    """Bind the HTTP server without starting it. Port 0 picks a free port; with ``tries`` > 1, a busy port
    moves on to the next one (port, port+1, ...)."""
    state = State(project, read_only=read_only)
    title = project.inputs[0].stem if len(project.inputs) == 1 else "diagram"
    server = None
    for p in range(port, port + max(tries, 1)) if port else [0]:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), _handler(state, title))
            break
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
    if server is None:
        last = port + max(tries, 1) - 1
        span = f"ports {port}-{last} are" if last > port else f"port {port} is"
        raise PortInUse(f"{span} already in use (another qdbd serve?); pick one with --port")
    server.daemon_threads = True
    return server, state


def poll_once(state: State) -> bool:
    """Reload if any schema file changed; returns True when a reload happened."""
    if not state.changed():
        return False
    try:
        state.reload()
    except Exception as e:  # keep serving on unexpected errors
        print(f"[qdbd] reload failed: {e}", file=sys.stderr, flush=True)
    return True


def serve(
    project: Project, port: int = 8765, open_browser: bool = True, read_only: bool = False, tries: int = 1
) -> int:
    try:
        server, state = make_server(project, port, read_only=read_only, tries=tries)
    except PortInUse as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for d in state.diagnostics:
        print(d["text"], file=sys.stderr)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if read_only:
        print(f"[qdbd] serving {len(state.files)} file(s) read-only at {url}")
        print(f"[qdbd] nothing is written to disk. To share it: cloudflared tunnel --url {url}")
    else:
        print(f"[qdbd] serving {len(state.files)} file(s) at {url}  (layout: {display_path(project.sidecar)})")
    print("[qdbd] Ctrl+C to stop", flush=True)

    def watch() -> None:
        while True:
            time.sleep(0.3)
            poll_once(state)

    threading.Thread(target=watch, daemon=True).start()
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[qdbd] stopped")
    finally:
        server.server_close()
    return 0
