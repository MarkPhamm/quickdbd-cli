"""DBML parser (dbdiagram.io's schema language, https://dbml.dbdiagram.io/docs/).

A DBML file becomes the same per-file ``FileParse`` the QuickDBD parser produces, so a folder can mix both
syntaxes: all tables share one namespace and go through the one resolve step in ``parser.py``.

The reference is @dbml/parse 10.3.1 (github.com/holistics/dbml, the parser dbdiagram.io runs); its snapshot tests
are the acceptance corpus in ``tests/fixtures/dbml-ref``. Error wording is qdbd's own, on the reference's line.
Constructs qdbd doesn't draw (enums, checks, records, deps, project settings, ...) are parsed, checked and listed in
``FileParse.unmodelled`` so ``qdbd convert`` can say what it drops.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .model import Column, Diagnostic, Table
from .parser import COLOR_RE, HEX_RE, TAG_NAME_RE, TAG_RE, FileParse, PendingRel, encode, split_tags

# Relationship operator -> (cardinality of the left end, of the right end). A `?` makes its own side optional.
_BASE = {"-": ("one", "one"), "<>": ("many", "many"), ">": ("many", "one"), "<": ("one", "many")}
_OPTIONAL = {"one": "zeroOne", "many": "zeroMany"}
REL_OPS: dict[str, tuple[str, str]] = {}
for _op, (_l, _r) in _BASE.items():
    for _pre in ("", "?"):
        for _post in ("", "?"):
            REL_OPS[_pre + _op + _post] = (_OPTIONAL[_l] if _pre else _l, _OPTIONAL[_r] if _post else _r)

REF_ACTIONS = {"cascade", "restrict", "set null", "set default", "no action"}
INDEX_TYPES = {"btree", "hash", "gin", "gist", "brin", "spgist"}
TOP_LEVEL = {"table", "tablepartial", "ref", "enum", "tablegroup", "project"}
TOP_ONLY = {"table", "tablepartial", "enum", "tablegroup", "project"}  # never inside another element
ELEMENTS = {
    "table", "tablepartial", "ref", "enum", "tablegroup", "project", "note", "records", "dep", "metadata",
    "diagramview", "use", "reuse",
}  # fmt: skip


# --------------------------------------------------------------------------- lexer


@dataclass
class Tok:
    kind: str  # ident quoted str func color num op . ~ * { } [ ] ( ) , : ; nl eof
    value: str
    line: int
    space: bool = False  # whitespace (or a line start) right before it
    multiline: bool = False  # a '''string'''

    def __repr__(self) -> str:  # for error messages
        return {"nl": "end of line", "eof": "end of file"}.get(self.kind, self.value or self.kind)


def _is_alpha(ch: str) -> bool:
    return ch == "_" or ch.isalpha() or unicodedata.category(ch).startswith("M")


def _is_alnum(ch: str) -> bool:
    return _is_alpha(ch) or "0" <= ch <= "9"


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "`": "`", "0": "\0", "b": "\b",
            "v": "\v", "f": "\f", " ": " "}  # fmt: skip


class _Lexer:
    def __init__(self, text: str, fp: FileParse):
        self.s = text
        self.i = 0
        self.line = 1
        self.fp = fp
        self.toks: list[Tok] = []
        self.comments: dict[int, str] = {}  # line -> text of a `//` comment
        self.code_lines: set[int] = set()  # lines holding something other than comments

    def error(self, line: int, msg: str) -> None:
        self.fp.error(line, msg)

    def add(self, kind: str, value: str, line: int, space: bool, multiline: bool = False) -> None:
        self.toks.append(Tok(kind, value, line, space, multiline))
        if kind != "nl":
            self.code_lines.add(line)

    def run(self) -> list[Tok]:
        s = self.s
        space = True
        while self.i < len(s):
            c = s[self.i]
            start_line = self.line
            if c in " \t\r﻿":
                self.i += 1
                space = True
                continue
            if c == "\n":
                self.add("nl", "", self.line, space)
                self.i += 1
                self.line += 1
                space = True
                continue
            if s.startswith("//", self.i):
                end = s.find("\n", self.i)
                end = len(s) if end == -1 else end
                self.comments[self.line] = s[self.i + 2 : end].strip()
                self.i = end
                space = True
                continue
            if s.startswith("/*", self.i):
                end = s.find("*/", self.i + 2)
                if end == -1:
                    self.error(start_line, "Unclosed /* comment")
                    end = len(s) - 2
                self.line += s.count("\n", self.i, end + 2)
                self.i = end + 2
                space = True
                continue
            if c in "{}[](),:;.~*":
                self.add(c, c, self.line, space)
                self.i += 1
            elif s.startswith("'''", self.i):
                self.add("str", self._string("'''", True), start_line, space, multiline=True)
            elif c == "'":
                self.add("str", self._string("'", False), start_line, space)
            elif c == '"':
                self.add("quoted", self._string('"', False), start_line, space)
            elif c == "`":
                end = s.find("`", self.i + 1)
                if end == -1:
                    self.error(start_line, "Unclosed ` expression")
                    end = len(s)
                value = s[self.i + 1 : end].replace("\r\n", "\n")
                self.line += value.count("\n")
                self.i = end + 1
                self.add("func", value, start_line, space)
            elif c == "#":
                j = self.i + 1
                while j < len(s) and _is_alnum(s[j]):
                    j += 1
                self.add("color", s[self.i : j], start_line, space)
                self.i = j
            elif c in "<>-?=!+/%&|^":
                self.add("op", self._operator(), start_line, space)
            elif _is_alpha(c):
                j = self.i + 1
                while j < len(s) and _is_alnum(s[j]):
                    j += 1
                self.add("ident", s[self.i : j], start_line, space)
                self.i = j
            elif "0" <= c <= "9":
                self._number(space)
            else:
                self.error(start_line, f"Unexpected character '{c}'")
                self.i += 1
            space = False
        self.add("nl", "", self.line, space)
        self.toks.append(Tok("eof", "", self.line, True))
        return self.toks

    def _string(self, quote: str, multiline: bool) -> str:
        s, start = self.s, self.line
        self.i += len(quote)
        out: list[str] = []
        while True:
            if self.i >= len(s):
                self.error(start, "Unclosed string")
                break
            c = s[self.i]
            if s.startswith(quote, self.i):
                self.i += len(quote)
                break
            if c == "\r" and s.startswith("\n", self.i + 1):
                self.i += 1
                continue
            if c == "\n":
                if not multiline:
                    self.error(start, "Unclosed string (strings can't span lines; use '''...''')")
                    break
                self.line += 1
            if c == "\\" and self.i + 1 < len(s):
                nxt = s[self.i + 1]
                if nxt == "\n":  # a line continuation
                    self.line += 1
                    self.i += 2
                    continue
                if nxt == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", s[self.i + 2 : self.i + 6]):
                    out.append(chr(int(s[self.i + 2 : self.i + 6], 16)))
                    self.i += 6
                    continue
                out.append(_ESCAPES.get(nxt, "\\" + nxt))
                self.i += 2
                continue
            out.append(c)
            self.i += 1
        return "".join(out)

    def _operator(self) -> str:
        s, i = self.s, self.i
        for op in ("?<>?", "?<>", "<>?", "?>?", "?<?", "?-?", "<>", "<?", "<-", "<=", ">?", ">=", "->", "-?", "?-",
                   "?<", "?>", "==", "!="):  # fmt: skip
            if s.startswith(op, i):
                self.i += len(op)
                return op
        self.i += 1
        return s[i]

    def _number(self, space: bool) -> None:
        s, i, line = self.s, self.i, self.line
        j = i
        while j < len(s) and s[j].isdigit():
            j += 1
        if j < len(s) and _is_alpha(s[j]) and not re.match(r"[eE][+-]?\d", s[j : j + 3]):
            while j < len(s) and _is_alnum(s[j]):
                j += 1
            self.add("ident", s[i:j], line, space)  # e.g. `1st_name`
            self.i = j
            return
        if j < len(s) and s[j] == ".":
            j += 1
            if j >= len(s) or not s[j].isdigit():
                self.error(line, f"Invalid number '{s[i:j]}'")
                self.add("num", s[i:j], line, space)
                self.i = j
                return
            while j < len(s) and s[j].isdigit():
                j += 1
        m = re.match(r"[eE][+-]?\d+", s[j:])
        if m:
            j += m.end()
        if j < len(s) and _is_alpha(s[j]):
            self.error(line, f"Invalid number '{s[i : j + 1]}'")
        self.add("num", s[i:j], line, space)
        self.i = j


# --------------------------------------------------------------------------- statements


@dataclass
class Stmt:
    """A field line, or an element: header tokens then a `{ body }` or a `: simple body`."""

    kind: str  # "field" | "block" | "simple"
    toks: list[Tok]
    line: int
    end_line: int
    body: list[Stmt] = field(default_factory=list)
    simple: list[Tok] = field(default_factory=list)

    @property
    def keyword(self) -> str:
        return self.toks[0].value.lower() if self.toks and self.toks[0].kind == "ident" else ""


_OPEN, _CLOSE = "([", ")]"


class _Scanner:
    def __init__(self, toks: list[Tok], fp: FileParse):
        self.t = toks
        self.i = 0
        self.fp = fp

    def peek(self) -> Tok:
        return self.t[self.i]

    def block(self, top: bool, opened: Tok | None = None) -> tuple[list[Stmt], int]:
        """Statements up to the matching `}` (consumed); returns them and the `}` line."""
        out: list[Stmt] = []
        while True:
            tok = self.peek()
            if tok.kind == "nl" or tok.kind == ";":
                self.i += 1
                continue
            if tok.kind == "eof":
                if not top:
                    self.fp.error(opened.line if opened else tok.line, "Missing '}' to close this block")
                return out, tok.line
            if tok.kind == "}":
                self.i += 1
                if top:
                    self.fp.error(tok.line, "Unexpected '}'")
                    continue
                return out, tok.line
            if not top and self._opens_top_level_block():
                # `Table c {` inside a block: the block above is missing its `}`. Close it here, so c and every
                # table after it still parse.
                where = f" (to close the block opened at line {opened.line})" if opened else ""
                self.fp.error(tok.line, f"Missing '}}' before this line{where}")
                last = next((t for t in reversed(self.t[: self.i]) if t.kind != "nl"), tok)
                return out, last.line
            stmt = self.statement(top)
            if stmt is not None:
                out.append(stmt)

    def _opens_top_level_block(self) -> bool:
        """The line here starts with a top-level-only element (Table, Enum, ...) and opens a `{` block."""
        tok = self.peek()
        if tok.kind != "ident" or tok.value.lower() not in TOP_ONLY:
            return False
        j = self.i
        while self.t[j].kind not in ("nl", "eof", "{", "}"):
            j += 1
        return self.t[j].kind == "{"

    def _skip_newlines_to(self, kinds: tuple[str, ...]) -> bool:
        """Past the newlines here, if what follows them is one of `kinds` (a `{` on the line below a header)."""
        j = self.i
        while self.t[j].kind == "nl":
            j += 1
        if j > self.i and self.t[j].kind in kinds:
            self.i = j
            return True
        return False

    def _ref_continuation(self, toks: list[Tok]) -> list[Tok]:
        """A `Ref:` relationship broken across lines: `Ref:` alone, or a line ending in, or the next one starting
        with, the operator."""
        while True:
            dangling = not toks or (toks[-1].kind == "op" and toks[-1].value in REL_OPS)
            j = self.i
            while self.t[j].kind == "nl":
                j += 1
            leading = (
                self.t[j].kind == "op"
                and self.t[j].value in REL_OPS
                and not any(t.kind == "op" and t.value in REL_OPS for t in toks)
            )
            if j == self.i or not (dangling or leading) or self.t[j].kind == "eof":
                return toks
            self.i = j
            toks = toks + self._until_line_end(braces=False)

    def _until_line_end(self, braces: bool) -> list[Tok]:
        """Tokens to the end of the line, keeping `(`/`[` groups (which may span lines) whole."""
        toks: list[Tok] = []
        depth: list[Tok] = []
        while True:
            tok = self.peek()
            if tok.kind == "eof":
                break
            if tok.kind in "{}" and not braces:
                if depth:
                    self.fp.error(depth[-1].line, f"Missing '{_CLOSE[_OPEN.index(depth[-1].kind)]}'")
                break
            if tok.kind == "nl" and not depth:
                break
            self.i += 1
            if tok.kind in _OPEN or (braces and tok.kind == "{"):
                depth.append(tok)
            elif tok.kind in _CLOSE or (braces and tok.kind == "}"):
                if depth:
                    depth.pop()
                else:
                    self.fp.error(tok.line, f"Unexpected '{tok.kind}'")
                    continue
            if tok.kind != "nl":
                toks.append(tok)
        if depth and self.peek().kind == "eof":
            self.fp.error(depth[-1].line, f"Missing '{_CLOSE[_OPEN.index(depth[-1].kind)]}'")
        return toks

    def statement(self, top: bool = False) -> Stmt | None:
        first = self.peek()
        if first.kind == "ident" and first.value.lower() in ("use", "reuse"):
            toks = self._until_line_end(braces=True)
            return Stmt("field", toks, first.line, toks[-1].line if toks else first.line)
        # At the top level, an element's header may continue on the next lines (`Table users` then `{`), as in
        # dbdiagram.io. Inside a block it can't: `indexes` alone on its line is a column there.
        element = top and first.kind == "ident" and first.value.lower() in ELEMENTS
        toks: list[Tok] = []
        depth: list[Tok] = []
        while True:
            tok = self.peek()
            if tok.kind == "nl" and not depth and element:
                if self._skip_newlines_to(("{",)) or (len(toks) == 1 and self._skip_newlines_to(("ident", "quoted"))):
                    continue  # `Table users` then `{`; or `Table` then `users {`
            if tok.kind == "eof" or (tok.kind == "nl" and not depth):
                break
            if tok.kind in "{}":
                if depth:  # an unclosed `(` or `[`: report it, end the statement here
                    self.fp.error(depth[-1].line, f"Missing '{_CLOSE[_OPEN.index(depth[-1].kind)]}'")
                    depth = []
                if tok.kind == "}":
                    break
                self.i += 1
                body, end = self.block(top=False, opened=tok)
                if not toks:
                    self.fp.error(tok.line, "Expected an element name before '{'")
                    return None
                return Stmt("block", toks, first.line, end, body=body)
            if tok.kind == ":" and not depth and toks:
                self.i += 1
                simple = self._until_line_end(braces=False)
                if element and first.value.lower() == "ref":
                    simple = self._ref_continuation(simple)
                end = simple[-1].line if simple else tok.line
                return Stmt("simple", toks, first.line, end, simple=simple)
            self.i += 1
            if tok.kind in _OPEN:
                depth.append(tok)
            elif tok.kind in _CLOSE:
                if depth and _OPEN.index(depth[-1].kind) == _CLOSE.index(tok.kind):
                    depth.pop()
                else:
                    self.fp.error(tok.line, f"Unexpected '{tok.kind}'")
                    continue
            if tok.kind != "nl":
                toks.append(tok)
        if depth:
            self.fp.error(depth[-1].line, f"Missing '{_CLOSE[_OPEN.index(depth[-1].kind)]}'")
        if not toks:
            return None
        return Stmt("field", toks, first.line, toks[-1].line)


# --------------------------------------------------------------------------- token helpers


def _split_settings(toks: list[Tok]) -> tuple[list[Tok], list[Tok] | None]:
    """(tokens before, tokens inside) a trailing `[settings]` list; a `[` glued to the previous token is an array
    type (`int[]`), not settings."""
    if not toks or toks[-1].kind != "]":
        return toks, None
    depth = 0
    for k in range(len(toks) - 1, -1, -1):
        if toks[k].kind == "]":
            depth += 1
        elif toks[k].kind == "[":
            depth -= 1
            if depth == 0:
                if k > 0 and not toks[k].space and toks[k - 1].kind in ("ident", "quoted", "]", ")"):
                    return toks, None
                return toks[:k], toks[k + 1 : -1]
    return toks, None


def _split_commas(toks: list[Tok]) -> list[list[Tok]]:
    out: list[list[Tok]] = [[]]
    depth = 0
    for t in toks:
        if t.kind in _OPEN:
            depth += 1
        elif t.kind in _CLOSE:
            depth -= 1
        if t.kind == "," and depth == 0:
            out.append([])
        else:
            out[-1].append(t)
    return out


@dataclass
class Setting:
    key: str  # lowercased, words joined by one space
    value: list[Tok] | None
    line: int


def _name_tok(t: Tok) -> bool:
    return t.kind in ("ident", "quoted")


def _dotted(toks: list[Tok], at: int = 0) -> tuple[list[str], int]:
    """A `a.b."c"` name from toks[at]; returns the parts and the index after it."""
    parts: list[str] = []
    i = at
    while i < len(toks) and _name_tok(toks[i]):
        parts.append(toks[i].value)
        i += 1
        if i < len(toks) and toks[i].kind == "." and i + 1 < len(toks) and _name_tok(toks[i + 1]):
            i += 1
        else:
            break
    return parts, i


def _display(schema: str | None, name: str) -> str:
    return name if schema in (None, "public") else f"{schema}.{name}"


# --------------------------------------------------------------------------- interpreter


@dataclass
class _RawField:
    name: str
    typ: str
    line: int
    settings: list[Setting]
    stmt: Stmt


@dataclass
class _Index:
    columns: list[str]
    pk: bool
    unique: bool
    expressions: int
    line: int


@dataclass
class _RawTable:
    kind: str  # "table" | "partial"
    schema: str | None
    name: str
    alias: str | None
    line: int
    end_line: int
    items: list = field(default_factory=list)  # _RawField, or ("~", partial name, line)
    indexes: list[_Index] = field(default_factory=list)
    note: list[str] | None = None
    color: str | None = None


@dataclass
class _RefEnd:
    parts: list[str]  # schema/table names; the last one is the table
    columns: list[str]
    line: int


class _Interpreter:
    def __init__(self, fp: FileParse, stmts: list[Stmt], comments: dict[int, str], code_lines: set[int]):
        self.fp = fp
        self.stmts = stmts
        self.comments = comments
        self.code_lines = code_lines
        self.tables: dict[tuple[str, str], _RawTable] = {}  # (schema, name) -> table
        self.partials: dict[str, _RawTable] = {}
        self.aliases: dict[str, tuple[str, str]] = {}
        self.refs: list[tuple[_RefEnd, str, _RefEnd, int]] = []
        self.groups: list[tuple[str, list[tuple[list[str], int]], int]] = []
        self.built: dict[tuple[str, str], Table] = {}
        self.deps: list[tuple[list[Tok], list[Tok], int]] = []
        self.sticky: set[str] = set()
        self.enum_defaults: list[tuple[list[str], int]] = []  # `default: status.active` to check once enums are known

    # -- diagnostics ----------------------------------------------------------------
    def error(self, line: int, msg: str) -> None:
        self.fp.error(line, msg)

    def warning(self, line: int, msg: str) -> None:
        self.fp.diagnostics.append(Diagnostic(self.fp.path, line, msg, "warning"))

    def unmodelled(self, line: int, what: str) -> None:
        self.fp.unmodelled.append((line, what))

    # -- settings -------------------------------------------------------------------
    def settings(self, toks: list[Tok] | None) -> list[Setting]:
        out: list[Setting] = []
        if toks is None:
            return out
        if not toks:
            return out
        for part in _split_commas(toks):
            if not part:
                self.error(toks[0].line, "Empty setting")
                continue
            colon = next((k for k, t in enumerate(part) if t.kind == ":"), None)
            key_toks = part if colon is None else part[:colon]
            if not key_toks or not all(t.kind == "ident" for t in key_toks):
                self.error(part[0].line, f"Invalid setting '{' '.join(t.value for t in part)}'")
                continue
            key = " ".join(t.value.lower() for t in key_toks)
            out.append(Setting(key, None if colon is None else part[colon + 1 :], part[0].line))
        return out

    def _once(self, settings: list[Setting]) -> None:
        seen: set[str] = set()
        for s in settings:
            if s.key in seen and s.key not in ("ref", "check"):
                self.error(s.line, f"'{s.key}' can only appear once")
            seen.add(s.key)

    def _string_value(self, s: Setting) -> str | None:
        if s.value and len(s.value) == 1 and s.value[0].kind in ("str", "quoted"):
            return _normalize_note(s.value[0].value) if s.value[0].multiline else s.value[0].value
        self.error(s.line, f"'{s.key}' must be a string")
        return None

    def _color_value(self, s: Setting) -> str | None:
        if s.value and len(s.value) == 1 and s.value[0].kind == "color" and HEX_RE.match(s.value[0].value):
            return _hex6(s.value[0].value)
        self.error(s.line, f"'{s.key}' must be a color like #1e88e5")
        return None

    def _custom(self, s: Setting) -> None:
        """Custom metadata (`[owner: "data-team"]`): a string or a colour."""
        if s.value and len(s.value) == 1 and s.value[0].kind in ("str", "quoted", "color"):
            self.unmodelled(s.line, f"setting '{s.key}'")
        else:
            self.error(s.line, f"Unknown setting '{s.key}'" if s.value is None else f"'{s.key}' must be a string")

    # -- top level ------------------------------------------------------------------
    def run(self) -> None:
        for st in self.stmts:
            kw = st.keyword
            if kw == "table":
                self.table(st, "table")
            elif kw == "tablepartial":
                self.table(st, "partial")
            elif kw == "ref":
                self.ref_element(st)
            elif kw == "enum":
                self.enum(st)
            elif kw == "tablegroup":
                self.group(st)
            elif kw in ("use", "reuse"):
                self.use(st)
            elif kw == "dep":
                self.dep(st)
            elif kw in ("project", "note", "records", "metadata", "diagramview"):
                self.other(st, kw)
            else:
                what = st.toks[0].value if st.toks else "?"
                self.error(st.line, f"Unknown element '{what}' (expected Table, Ref, Enum, TableGroup, ...)")
        self.build_tables()
        self.resolve_refs()
        self.resolve_groups()
        self.resolve_deps()
        self.check_enum_defaults()
        self.colors()

    def other(self, st: Stmt, kw: str) -> None:
        for sub in st.body:
            if sub.kind != "field" and sub.keyword in TOP_LEVEL:
                self.error(sub.line, f"{sub.toks[0].value} must appear top-level")
        if kw == "note" and st.kind == "simple":
            self.error(st.line, "A top-level Note needs a name: Note name { '...' }")
            return
        if kw == "note":
            head, _ = _split_settings(st.toks[1:])
            if len(head) != 1 or not _name_tok(head[0]) or not head[0].value.strip():
                self.error(st.line, "Invalid name for a sticky note")
                return
            if head[0].value in self.sticky:
                self.error(st.line, f"Duplicate Note '{head[0].value}'")
                return
            self.sticky.add(head[0].value)
        if kw == "records":
            self.records(st, None)
            return
        self.unmodelled(st.line, {"note": "sticky note", "diagramview": "DiagramView"}.get(kw, kw.capitalize()))

    def use(self, st: Stmt) -> None:
        if any(t.kind == "ident" and t.value.lower() == "as" for t in st.toks):
            self.error(st.line, "qdbd can't rename imports (`as`); its files share one namespace")
        else:
            self.warning(st.line, "qdbd ignores `use`; pass the imported file or its folder too")

    def dep(self, st: Stmt) -> None:
        lines = [st.simple] if st.kind == "simple" else [s.toks for s in st.body if s.kind == "field"]
        if st.kind == "field":
            lines = [st.toks[1:]]
        for toks in lines:
            toks, _ = _split_settings(toks)
            ops = [k for k, t in enumerate(toks) if t.kind == "op"]
            if ops and all(toks[k].value in ("->", "<-") for k in ops):
                self.unmodelled(toks[0].line, "Dep")
                cuts = [-1, *ops, len(toks)]
                sides = [toks[a + 1 : b] for a, b in zip(cuts, cuts[1:], strict=False)]
                for k, (a, b) in enumerate(zip(sides, sides[1:], strict=False)):
                    up, down = (a, b) if toks[ops[k]].value == "->" else (b, a)
                    self.deps.append((up, down, toks[0].line))
            elif toks:
                self.error(toks[0].line, "Dep edges must use '->' or '<-'")

    def records(self, st: Stmt, table: _RawTable | None) -> None:
        if st.kind != "block":
            self.error(st.line, "Records need a { body }")
            return
        self.unmodelled(st.line, "records")

    # -- tables ---------------------------------------------------------------------
    def table(self, st: Stmt, kind: str) -> None:
        label = "Table" if kind == "table" else "TablePartial"
        if st.kind != "block":
            self.error(st.line, f"A {label} needs a {{ body }}")
            return
        head, settings_toks = _split_settings(st.toks[1:])
        parts, i = _dotted(head)
        if not parts:
            self.error(st.line, f"A {label} must have a name")
            return
        alias = None
        if i < len(head) and head[i].kind == "ident" and head[i].value.lower() == "as":
            if i + 1 < len(head) and _name_tok(head[i + 1]):
                alias = head[i + 1].value
                i += 2
            else:
                self.error(head[i].line, "Expected an alias after 'as'")
                i = len(head)
        if i < len(head):
            self.error(head[i].line, f"Unexpected '{head[i]!r}' in the {label} header")
        if len(parts) > 2 or (kind == "partial" and len(parts) > 1):
            self.error(st.line, f"Invalid {label} name '{'.'.join(parts)}'")
            return
        schema = parts[0] if len(parts) == 2 else None
        t = _RawTable(kind, schema, parts[-1], alias, st.line, st.end_line)
        settings = self.settings(settings_toks)
        self._once(settings)
        for s in settings:
            if s.key == "headercolor":
                t.color = self._color_value(s)
            elif s.key == "note":
                note = self._string_value(s)
                t.note = _doc_lines(note) if note is not None else None
            elif s.key == "dep" and s.value is not None:
                self.unmodelled(s.line, "Dep")
            else:
                self._custom(s)
        note_set = False  # a body Note replaces the header's note; two body Notes are an error
        for sub in st.body:
            kw = sub.keyword
            if sub.kind != "field" and kw == "note":
                if note_set:
                    self.error(sub.line, "Duplicate notes are defined")
                note = self._note_body(sub)
                if note is not None:
                    t.note = _doc_lines(note)
                note_set = True
            elif sub.kind == "block" and kw in ("indexes", "checks") and len(sub.toks) > 1:
                self.error(sub.line, f"'{sub.toks[0].value}' takes no name or arguments")
            elif sub.kind == "block" and kw == "indexes":
                self.indexes(sub, t)
            elif sub.kind == "block" and kw == "checks":
                self.unmodelled(sub.line, "checks")
            elif sub.kind == "block" and kw == "records":
                self.records(sub, t)
            elif kw in ("table", "ref", "enum", "tablegroup", "tablepartial", "project") and sub.kind != "field":
                self.error(sub.line, f"{sub.toks[0].value} must appear top-level")
            elif sub.kind != "field":
                self.error(sub.line, f"Unknown element '{sub.toks[0].value}' inside a {label}")
            elif sub.toks[0].kind == "~":
                if len(sub.toks) == 2 and _name_tok(sub.toks[1]):
                    names = [x[1] for x in t.items if isinstance(x, tuple)]
                    if sub.toks[1].value in names:
                        self.error(sub.line, f"Duplicate table partial injection '{sub.toks[1].value}'")
                    else:
                        t.items.append(("~", sub.toks[1].value, sub.line))
                else:
                    self.error(sub.line, "Expected a partial name after '~'")
            else:
                f = self.column(sub)
                if f is not None:
                    t.items.append(f)
        if kind == "partial":
            own = {f.name for f in t.items if isinstance(f, _RawField)}
            for ix in t.indexes:
                missing = [c for c in ix.columns if c not in own]
                if missing:
                    self.error(ix.line, f"No column named '{missing[0]}' inside TablePartial '{t.name}'")
            for f in t.items:
                for s in f.settings if isinstance(f, _RawField) else []:
                    v = s.value or []
                    if s.key == "ref" and len(v) == 2 and _name_tok(v[1]) and v[1].value == f.name:
                        self.error(s.line, "Two endpoints are the same")
            if t.name in self.partials:
                self.error(st.line, f"TablePartial '{t.name}' already exists")
                return
            self.partials[t.name] = t
            return
        key = (schema or "public", t.name)
        if key in self.tables:
            self.error(st.line, f"Table '{t.name}' already exists in schema '{key[0]}'")
            return
        if alias is not None:
            clash = alias in self.aliases or ("public", alias) in self.tables
            if clash:
                self.error(st.line, f"Table '{alias}' already exists in schema 'public'")
            else:
                self.aliases[alias] = key
        if ("public", t.name) in self.aliases.values() or (schema in (None, "public") and t.name in self.aliases):
            if t.name in self.aliases and self.aliases[t.name] != key:
                self.error(st.line, f"Table '{t.name}' already exists in schema 'public'")
        self.tables[key] = t

    def _note_body(self, sub: Stmt) -> str | None:
        toks = sub.simple if sub.kind == "simple" else [t for s in sub.body for t in s.toks]
        if len(toks) == 1 and toks[0].kind in ("str", "quoted"):
            return _normalize_note(toks[0].value) if toks[0].multiline else toks[0].value
        self.error(sub.line, "A Note must be a string")
        return None

    def column(self, st: Stmt) -> _RawField | None:
        toks, settings_toks = _split_settings(st.toks)
        if not toks or not (_name_tok(toks[0]) or toks[0].kind == "num"):
            self.error(st.line, f"Invalid column '{' '.join(t.value for t in st.toks)}'")
            return None
        name = toks[0].value
        if len(toks) == 1:
            self.error(st.line, "A column must have a type")
            return None
        typed = self._type(toks[1:], st.line)
        if typed is None:
            return None
        typ, rest = typed
        settings = self.settings(settings_toks)
        for t in rest:  # old syntax: `id int pk unique`
            if t.kind != "ident":
                self.error(t.line, "These fields must be some inline settings optionally ended with a setting list")
                return None
            if t.value.lower() not in ("pk", "unique"):
                self.error(t.line, "Inline column settings can only be `pk` or `unique`")
                continue
            settings.append(Setting(t.value.lower(), None, t.line))
        self._once(settings)
        flags = {s.key for s in settings if s.value is None}
        if "null" in flags and "not null" in flags:
            self.error(st.line, "A column can't be both null and not null")
        if "pk" in flags and "primary key" in flags:
            self.error(st.line, "'pk' and 'primary key' mean the same thing; use one")
        for s in settings:
            if s.value is None and s.key not in ("pk", "primary key", "null", "not null", "unique", "increment"):
                self.error(s.line, f"Unknown column setting '{s.key}'")
            elif s.key == "dep" and s.value is not None:
                self.unmodelled(s.line, "Dep")
            elif s.value is not None and s.key not in ("note", "default", "ref", "check"):
                self._custom(s)
            elif s.key == "check":
                if not (s.value and len(s.value) == 1 and s.value[0].kind == "func"):
                    self.error(s.line, "'check' must be a function expression")
                else:
                    self.unmodelled(s.line, "check")
            elif s.key == "note":
                self._string_value(s)
            elif s.key == "default":
                self._check_default(s)
        return _RawField(name, typ, st.line, settings, st)

    def _check_default(self, s: Setting) -> None:
        bad = "'default' must be an enum value, a string, number, `expression`, true, false or null"
        v = s.value or []
        if len(v) == 1 and v[0].kind == "ident" and v[0].value.lower() not in ("true", "false", "null"):
            self.error(s.line, bad)
        elif _default(v) is None:
            self.error(s.line, bad)
        elif len(v) > 1 and v[-1].kind != "num":
            parts, _ = _dotted(v)
            if len(parts) > 3:
                self.error(s.line, bad)
            else:
                self.enum_defaults.append((parts, s.line))

    def _type(self, toks: list[Tok], line: int) -> tuple[str, list[Tok]] | None:
        parts, i = _dotted(toks)
        if not parts:
            self.error(line, f"Invalid column type '{' '.join(t.value for t in toks)}'")
            return None
        if len(parts) > 2:
            self.error(line, "Invalid column type")
            return None
        out = ".".join(parts)
        while i < len(toks):
            t = toks[i]
            if t.kind == "(":
                j = i + 1
                depth = 1
                while j < len(toks) and depth:
                    depth += {"(": 1, ")": -1}.get(toks[j].kind, 0)
                    j += 1
                args = []
                for a in _split_commas(toks[i + 1 : j - 1]):
                    args.append("".join(x.value for x in a))
                out += "(" + ",".join(args) + ")"
                i = j
            elif t.kind == "[" and not t.space:
                j = i + 1
                while j < len(toks) and toks[j].kind != "]":
                    j += 1
                out += "[" + ",".join(x.value for x in toks[i + 1 : j] if x.kind != ",") + "]"
                i = j + 1
            else:
                break
        return out, toks[i:]

    def indexes(self, st: Stmt, t: _RawTable) -> None:
        for sub in st.body:
            if sub.kind != "field":
                self.error(sub.line, "Expected an index: a column, (columns) or `expression`")
                continue
            toks, settings_toks = _split_settings(sub.toks)
            if toks and toks[0].kind == "(" and toks[-1].kind == ")":
                items = _split_commas(toks[1:-1])
            else:
                items = [[x] for x in toks]
            cols: list[str] = []
            exprs = 0
            ok = bool(items)
            for item in items:
                if len(item) == 1 and _name_tok(item[0]):
                    cols.append(item[0].value)
                elif len(item) == 1 and item[0].kind == "func":
                    exprs += 1
                else:
                    ok = False
            if not ok:
                self.error(sub.line, "Expected an index: a column, (columns) or `expression`")
                continue
            settings = self.settings(settings_toks)
            self._once(settings)
            pk = unique = False
            for s in settings:
                if s.key == "pk" and s.value is None:
                    pk = True
                elif s.key == "unique" and s.value is None:
                    unique = True
                elif s.key in ("name", "note") and s.value is not None:
                    self._string_value(s)
                elif s.key == "type" and s.value is not None:
                    v = s.value[0].value.lower() if len(s.value) == 1 else ""
                    if v not in INDEX_TYPES:
                        self.error(s.line, f"Unknown index type '{' '.join(x.value for x in s.value)}'")
                else:
                    self.error(s.line, f"Unknown index setting '{s.key}'")
            if exprs:
                self.unmodelled(sub.line, "expression index")
            elif len(cols) > 1 and not pk:
                self.unmodelled(sub.line, f"composite index ({', '.join(cols)}), drawn as INDEX on each column")
            t.indexes.append(_Index(cols, pk, unique, exprs, sub.line))

    def enum(self, st: Stmt) -> None:
        if st.kind != "block":
            self.error(st.line, "An Enum needs a { body }")
            return
        parts, i = _dotted(st.toks, 1)
        if not parts or len(parts) > 2 or i < len(st.toks):
            self.error(st.line, "Invalid Enum name")
            return
        values: list[str] = []
        for sub in st.body:
            toks, settings_toks = _split_settings(sub.toks)
            if sub.kind != "field" or len(toks) != 1 or toks[0].kind not in ("ident", "quoted", "num"):
                self.error(sub.line, "Invalid enum value")
                continue
            if toks[0].value in values:
                self.error(sub.line, f"Duplicate enum field '{toks[0].value}'")
                continue
            for s in self.settings(settings_toks):
                if s.key == "note" and s.value is not None:
                    self._string_value(s)
                else:
                    self.error(s.line, f"Unknown enum value setting '{s.key}'")
            values.append(toks[0].value)
        if not values:
            self.error(st.line, "An Enum must have at least one value")
            return
        name = _display(parts[0] if len(parts) == 2 else None, parts[-1])
        if name in self.fp.enums:
            self.error(st.line, f"Enum '{name}' already exists")
            return
        self.fp.enums[name] = values
        self.unmodelled(st.line, f"enum {name}")

    def group(self, st: Stmt) -> None:
        if st.kind != "block":
            self.error(st.line, "A TableGroup needs a { body }")
            return
        head, settings_toks = _split_settings(st.toks[1:])
        if len(head) != 1 or not _name_tok(head[0]):
            self.error(st.line, "A TableGroup name must be a single identifier")
            return
        settings = self.settings(settings_toks)
        self._once(settings)
        note_set = False
        for s in settings:
            if s.key == "color":
                self._color_value(s)
                self.unmodelled(s.line, "TableGroup colour")
            elif s.key == "note":
                self._string_value(s)
            else:
                self._custom(s)
        members: list[tuple[list[str], int]] = []
        for sub in st.body:
            if sub.kind != "field" and sub.keyword == "note":
                if note_set:
                    self.error(sub.line, "Duplicate notes are defined")
                self._note_body(sub)
                note_set = True
                continue
            parts, i = _dotted(sub.toks)
            if sub.kind != "field" or not parts or i < len(sub.toks) or len(parts) > 2:
                self.error(sub.line, "A TableGroup lists table names, one per line")
                continue
            members.append((parts, sub.line))
        name = head[0].value
        if any(g[0] == name for g in self.groups):
            self.error(st.line, f"TableGroup '{name}' already exists")
            return
        self.groups.append((name, members, st.line))

    # -- refs -----------------------------------------------------------------------
    def ref_element(self, st: Stmt) -> None:
        head = st.toks[1:]
        if st.kind == "field":
            self.error(st.line, "A Ref needs ':' or a { body }")
            return
        head, settings_toks = _split_settings(head)
        if settings_toks is not None:
            self.error(st.line, "A Ref shouldn't have a setting list (put settings after the relationship)")
        if len(head) > 1 or (head and not _name_tok(head[0])):
            self.error(st.line, "Invalid Ref name")
        lines = [st.simple] if st.kind == "simple" else [s.toks for s in st.body]
        for sub in st.body:
            if sub.kind != "field":
                self.error(sub.line, "Expected a relationship like a.id > b.id")
        if st.kind == "simple" and not st.simple:
            self.error(st.line, "Expected a relationship like a.id > b.id")
        for toks in lines:
            if toks:
                self.ref_expr(toks)

    def ref_expr(self, toks: list[Tok]) -> None:
        line = toks[0].line
        toks, settings_toks = _split_settings(toks)
        ops = [k for k, t in enumerate(toks) if t.kind == "op"]
        if len(ops) != 1 or toks[ops[0]].value not in REL_OPS:
            self.error(line, "Expected a relationship like a.id > b.id (operators: < > - <>, ? for optional)")
            return
        k = ops[0]
        left, right = self.endpoint(toks[:k], line), self.endpoint(toks[k + 1 :], line)
        for s in self.settings(settings_toks):
            if s.key in ("delete", "update"):
                v = " ".join(t.value.lower() for t in s.value or [])
                if v not in REF_ACTIONS:
                    self.error(s.line, f"'{s.key}' must be one of: {', '.join(sorted(REF_ACTIONS))}")
                else:
                    self.unmodelled(s.line, f"on {s.key} {v}")
            elif s.key == "color" and s.value is not None:
                if self._color_value(s):
                    self.unmodelled(s.line, "Ref colour")
            elif s.key == "inactive" and s.value is None:
                self.unmodelled(s.line, "inactive Ref")
            else:
                self.error(s.line, f"Unknown Ref setting '{s.key}'")
        if left and right:
            if len(left.columns) != len(right.columns):
                self.error(line, "Both sides of a composite Ref need the same number of columns")
                return
            self.refs.append((left, toks[k].value, right, line))

    def endpoint(self, toks: list[Tok], line: int, own: tuple[str, str] | None = None) -> _RefEnd | None:
        parts, i = _dotted(toks)
        if i < len(toks) and toks[i].kind == "." and i + 1 < len(toks) and toks[i + 1].kind == "(":
            cols = []
            for item in _split_commas(toks[i + 2 : -1] if toks[-1].kind == ")" else []):
                if len(item) == 1 and _name_tok(item[0]):
                    cols.append(item[0].value)
                else:
                    cols = []
                    break
            if not parts or not cols or toks[-1].kind != ")" or len(parts) > 2:
                self.error(line, "Invalid composite Ref endpoint")
                return None
            return _RefEnd(parts, cols, line)
        if not parts or i != len(toks):
            self.error(line, f"Invalid Ref endpoint '{' '.join(t.value for t in toks)}'")
            return None
        if len(parts) == 1:
            if own is None:
                self.error(line, f"A Ref endpoint needs a table: '{parts[0]}'")
                return None
            return _RefEnd([own[0], own[1]], parts, line)
        if len(parts) > 3:
            self.error(line, f"Invalid Ref endpoint '{'.'.join(parts)}'")
            return None
        return _RefEnd(parts[:-1], [parts[-1]], line)

    # -- building -------------------------------------------------------------------
    def _lookup(self, parts: list[str]) -> tuple[str, str] | None:
        if len(parts) == 1:
            if parts[0] in self.aliases:
                return self.aliases[parts[0]]
            key = ("public", parts[0])
        else:
            key = (parts[0], parts[1])
        return key if key in self.tables else None

    def build_tables(self) -> None:
        fp = self.fp
        for key, rt in self.tables.items():
            items = list(rt.items)
            note, color = rt.note, rt.color
            indexes = list(rt.indexes)
            # Partials: local definitions win, then the last partial injected (as @dbml/core merges them).
            names = {x.name for x in items if isinstance(x, _RawField)}
            for pos in range(len(items) - 1, -1, -1):
                item = items[pos]
                if not isinstance(item, tuple):
                    continue
                partial = self.partials.get(item[1])
                if partial is None:
                    self.error(item[2], f"TablePartial '{item[1]}' does not exist")
                    items[pos : pos + 1] = []
                    continue
                new = [f for f in partial.items if isinstance(f, _RawField) and f.name not in names]
                names |= {f.name for f in new}
                items[pos : pos + 1] = new
            for item in reversed([x for x in rt.items if isinstance(x, tuple)]):
                partial = self.partials.get(item[1])
                if partial is None:
                    continue
                if note is None and partial.note is not None:
                    note = partial.note
                if color is None and partial.color is not None:
                    color = partial.color
                indexes += partial.indexes
            display = _display(rt.schema, rt.name)
            t = Table(encode(display), display, fp.path, rt.line, [rt.alias] if rt.alias else [])
            t.end_line = rt.end_line
            t.color = color
            t.comments = list(note) if note else []
            for f in items:
                col = Column(encode(f.name), f.name, f.line, order=len(t.columns), type=f.typ)
                if col.id in t.columns:
                    self.error(f.line, f"Duplicate column '{f.name}'")
                    continue
                for s in f.settings:
                    if s.key in ("pk", "primary key"):
                        col.pk = True
                    elif s.key == "null":
                        col.nullable = True
                    elif s.key == "unique":
                        col.unique = True
                    elif s.key == "increment":
                        col.identity = True
                    elif s.key == "default":
                        col.default = _default(s.value)
                    elif s.key == "note" and s.value and s.value[0].kind in ("str", "quoted"):
                        v = s.value[0]
                        col.comments = _doc_lines(_normalize_note(v.value) if v.multiline else v.value)
                t.columns[col.id] = col
            for ix in indexes:
                missing = [c for c in ix.columns if encode(c) not in t.columns]
                if missing:
                    self.error(ix.line, f"No column named '{missing[0]}' inside Table '{rt.name}'")
                    continue
                cols = [t.columns[encode(c)] for c in ix.columns]
                for c in cols:
                    if ix.pk:
                        c.pk = True
                    elif ix.unique and len(cols) == 1 and not ix.expressions:
                        c.unique = True
                    else:
                        c.index = True
            self._tags(t)
            self.built[key] = t
            if t.id in fp.tables:
                self.error(rt.line, f"Table '{display}' already exists")
                continue
            fp.tables[t.id] = t
            if rt.alias:
                fp.aliases[rt.alias] = t.id
        # inline refs, in source order of their tables
        for key, rt in self.tables.items():
            t = self.built[key]
            fields = [x for x in rt.items if isinstance(x, _RawField)]
            for item in rt.items:
                if isinstance(item, tuple) and item[1] in self.partials:
                    fields += [f for f in self.partials[item[1]].items if isinstance(f, _RawField)]
            seen = set()
            for f in fields:
                if f.name in seen or encode(f.name) not in t.columns:
                    continue
                seen.add(f.name)
                for s in f.settings:
                    if s.key == "ref" and s.value is not None:
                        self.inline_ref(key, f, s)

    def inline_ref(self, key: tuple[str, str], f: _RawField, s: Setting) -> None:
        toks = s.value or []
        if not toks or toks[0].kind != "op" or toks[0].value not in REL_OPS:
            self.error(s.line, "Expected 'ref: > table.column' (operators: < > - <>, ? for optional)")
            return
        right = self.endpoint(toks[1:], s.line, own=key)
        if right is None:
            return
        if len(right.columns) != 1:
            self.error(s.line, "An inline ref can't be composite; use a top-level Ref")
            return
        left = _RefEnd([key[0], key[1]], [f.name], s.line)
        self.refs.append((left, toks[0].value, right, s.line))

    def _shown(self, end: _RefEnd) -> str:
        key = self._lookup(end.parts)
        if key is not None:
            return self.built[key].name
        return end.parts[-1] if len(end.parts) == 1 or end.parts[0] == "public" else ".".join(end.parts)

    def _resolve_end(self, end: _RefEnd) -> tuple[str, list[str]] | None:
        """(table id, column ids) for an endpoint; a table from another file is left to the global resolver."""
        key = self._lookup(end.parts)
        if key is None:
            if len(end.parts) == 1 or end.parts[0] == "public":
                return encode(end.parts[-1]), [encode(c) for c in end.columns]
            return encode(".".join(end.parts)), [encode(c) for c in end.columns]
        t = self.built[key]
        cols = []
        for c in end.columns:
            if encode(c) not in t.columns:
                self.error(end.line, f"Column '{c}' does not exist in Table '{t.name}'")
                return None
            cols.append(encode(c))
        return t.id, cols

    def resolve_refs(self) -> None:
        for left, op, right, line in self.refs:
            a, b = self._resolve_end(left), self._resolve_end(right)
            if a is None or b is None:
                continue
            if a[0] == b[0] and a[1] == b[1]:
                self.error(line, "Two endpoints are the same")
                continue
            pairs = zip(a[1], b[1], left.columns, right.columns, strict=True)
            for ca, cb, name_a, name_b in pairs:
                rel = PendingRel(f"{a[0]}.{ca}", op, f"{b[0]}.{cb}", self.fp.path, line, True)
                rel.cards = REL_OPS[op]
                rel.names = ((self._shown(left), name_a), (self._shown(right), name_b))
                self.fp.rels.append(rel)

    def resolve_groups(self) -> None:
        grouped: dict[tuple[str, str], str] = {}
        for name, members, group_line in self.groups:
            self.fp.groups[name] = group_line
            for parts, line in members:
                key = self._lookup(parts)
                if key is None:
                    schema = parts[0] if len(parts) == 2 else "public"
                    self.error(line, f"Table '{parts[-1]}' does not exist in schema '{schema}'")
                    continue
                if key in grouped:
                    self.error(line, f"Table '{parts[-1]}' is already in TableGroup '{grouped[key]}'")
                    continue
                grouped[key] = name
                self.built[key].group = name

    def _dep_end(self, toks: list[Tok], line: int) -> tuple | None:
        parts, i = _dotted(toks)
        if not parts or i != len(toks):
            self.error(line, "Invalid Dep endpoint")
            return None
        if len(parts) <= 2 and self._lookup(parts) is not None:
            return self._lookup(parts), None
        if len(parts) >= 2:
            key = self._lookup(parts[:-1])
            if key is not None:
                if encode(parts[-1]) not in self.built[key].columns:
                    self.error(line, f"Column '{parts[-1]}' does not exist in Table '{'.'.join(key)}'")
                    return None
                return key, parts[-1]
        if len(parts) == 1:
            self.error(line, f"Table '{parts[0]}' does not exist in schema 'public'")
        elif any(k[0] == parts[0] for k in self.tables) or len(parts) == 2:
            self.error(
                line, f"Table '{parts[-2] if len(parts) > 2 else parts[1]}' does not exist in schema '{parts[0]}'"
            )
        else:
            self.error(line, f"Schema or Table '{parts[0]}' does not exist")
        return None

    def resolve_deps(self) -> None:
        seen = set()
        for up, down, line in self.deps:
            a, b = self._dep_end(up, line), self._dep_end(down, line)
            if a is None or b is None:
                continue
            if (a, b) in seen:
                self.error(line, "Dep with same endpoints already exists")
            seen.add((a, b))

    def check_enum_defaults(self) -> None:
        for parts, line in self.enum_defaults:
            if len(parts) > 3:
                self.error(line, "'default' must be an enum value, a string, number, `expression`, true, false or null")
                continue
            enum = ".".join(p for p in parts[:-1] if p != "public") if parts[0] == "public" else ".".join(parts[:-1])
            if enum not in self.fp.enums:
                self.error(line, f"Enum '{enum}' does not exist")
            elif parts[-1] not in self.fp.enums[enum]:
                self.error(line, f"Enum '{enum}' has no value '{parts[-1]}'")

    # -- comments -------------------------------------------------------------------
    def _tags(self, t: Table) -> None:
        line = t.line - 1
        while line in self.comments and line not in self.code_lines:
            m = TAG_RE.match(self.comments[line])
            if m:
                target = t.dbt_tags if m.group(1).lower().startswith("dbt") else t.tags
                target[:0] = [x for x in split_tags(m.group(2)) if x not in target]
            line -= 1

    def colors(self) -> None:
        first_code = min(self.code_lines, default=0)
        self.fp.general_comments = [
            text for line, text in sorted(self.comments.items()) if line < first_code and not COLOR_RE.match(text)
        ]
        for line, text in sorted(self.comments.items()):
            m = COLOR_RE.match(text)
            if not m:
                continue
            parts = m.group(1).split()
            if len(parts) != 2 or not TAG_NAME_RE.match(parts[0]) or not HEX_RE.match(parts[1]):
                self.warning(line, "Invalid @color directive (use '// @color TAG #rrggbb')")
                continue
            self.fp.colors[parts[0].lower()] = (parts[1].lower(), line)


def _hex6(color: str) -> str:
    c = color.lower()
    return "#" + "".join(ch * 2 for ch in c[1:]) if len(c) == 4 else c


def _default(value: list[Tok] | None) -> str | None:
    if not value:
        return None
    if len(value) == 1:
        t = value[0]
        if t.kind in ("str", "quoted", "func"):
            return t.value
        if t.kind == "num":
            return t.value
        if t.kind == "ident":
            return t.value.lower()
    if all(t.kind == "op" and t.value in "+-" for t in value[:-1]) and value[-1].kind == "num":
        return "".join(t.value for t in value)
    parts, i = _dotted(value)
    if len(parts) >= 2 and i == len(value):  # an enum value: status.active
        return parts[-1]
    return None


def _doc_lines(note: str) -> list[str]:
    lines = note.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _normalize_note(text: str) -> str:
    """'''Multi-line''' strings: drop leading blank lines and the common indentation (as dbdiagram does)."""
    lines = text.split("\n")
    start = next((k for k, x in enumerate(lines) if x.strip()), len(lines))
    lines = lines[start:]
    filled = [x for x in lines if x.strip()]
    if not filled:
        return "\n".join(lines)
    indent = min(len(x) - len(x.lstrip()) for x in filled)
    return "\n".join(x[indent:] for x in lines)


def parse_dbml(text: str, path: str = "<input>") -> FileParse:
    fp = FileParse(path, syntax="dbml")
    fp.settings = {"casesensitive": True}
    lexer = _Lexer(text, fp)
    toks = lexer.run()
    stmts, _ = _Scanner(toks, fp).block(top=True)
    _Interpreter(fp, stmts, lexer.comments, lexer.code_lines).run()
    fp.diagnostics.sort(key=lambda d: d.line)
    return fp
