"""Embedded JavaScript runtime (V8 via mini-racer) for ELK layout and render.js.

mini-racer's built-in setTimeout does not work reliably, so a synchronous timer queue is
installed instead and drained from Python; ELK only uses setTimeout(0) to fake a worker.
"""

from __future__ import annotations

import atexit
import json
import time
from functools import cache
from importlib import resources

from py_mini_racer import JSTimeoutException, MiniRacer

_SHIM = """
globalThis.global = globalThis;
var __q = [];
globalThis.setTimeout = function (f) { __q.push(f); return __q.length; };
globalThis.clearTimeout = function () {};
function __drain() { var n = 0; while (__q.length) { __q.shift()(); n++; } return n; }
var __res = null, __err = null;
"""


class JSTimeout(RuntimeError):
    """A JavaScript call ran past its ``timeout_sec``; the runtime stays usable."""


def _asset(name: str) -> str:
    return resources.files("quickdbd_cli").joinpath(f"assets/{name}").read_text(encoding="utf-8")


class _Runtime:
    def __init__(self) -> None:
        self.ctx = MiniRacer()
        self.ctx.eval(_SHIM)
        self.loaded: set[str] = set()

    def load(self, name: str) -> None:
        if name not in self.loaded:
            self.ctx.eval(_asset(name))
            self.loaded.add(name)

    def _eval(self, code: str, deadline: float | None = None) -> object:
        if deadline is None:
            return self.ctx.eval(code)
        left = deadline - time.monotonic()
        try:
            if left <= 0:
                raise JSTimeoutException("deadline passed")
            return self.ctx.eval(code, timeout_sec=left)
        except JSTimeoutException:
            raise JSTimeout("JavaScript call timed out") from None

    def call(self, fn: str, *args, timeout_sec: float | None = None) -> object:
        """Call a global JS function with JSON-serialisable args; returns the JSON-decoded result."""
        argv = ", ".join(f"JSON.parse({json.dumps(json.dumps(a))})" for a in args)
        deadline = None if timeout_sec is None else time.monotonic() + timeout_sec
        return json.loads(self._eval(f"JSON.stringify({fn}({argv}))", deadline))

    def call_async(self, expr_fn: str, *args, timeout_sec: float | None = None) -> object:
        """Call a JS function returning a Promise, draining the timer queue until it settles."""
        argv = ", ".join(f"JSON.parse({json.dumps(json.dumps(a))})" for a in args)
        deadline = None if timeout_sec is None else time.monotonic() + timeout_sec
        self.ctx.eval("__res = null; __err = null; __q = [];")
        self._eval(
            f"Promise.resolve({expr_fn}({argv})).then("
            "function (r) { __res = JSON.stringify(r); }, function (e) { __err = String(e && e.stack || e); });",
            deadline,
        )
        for _ in range(10000):
            self._eval("__drain()", deadline)
            if self.ctx.eval("__res !== null || __err !== null"):
                break
        err = self.ctx.eval("__err")
        if err:
            raise RuntimeError(f"JavaScript error: {err}")
        res = self.ctx.eval("__res")
        if res is None:
            raise RuntimeError("JavaScript promise did not settle")
        return json.loads(res)

    def close(self) -> None:
        try:
            self.ctx.close()
        except Exception:
            pass


@cache
def runtime() -> _Runtime:
    rt = _Runtime()
    atexit.register(rt.close)
    return rt
