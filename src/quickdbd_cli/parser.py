"""QuickDBD schema parser.

This mirrors the behaviour of QuickDBD's own parser (app bundle v2.4.427.0) step by step,
including its error messages, so that any schema accepted by QuickDBD is accepted here and
produces the same tables, columns and relationships.

Deliberate deviations ("forgiving" mode) are accepted with a warning instead of an error, and
only where the input is unambiguous: tab characters, indented table headers/separators, spaces
inside a type's parentheses, an explicit ``NOT NULL``, and a ``[layout]`` line naming an
unknown table. ``default=`` values keep their original case (QuickDBD lowercases them).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import REL_TYPES, VIRTUAL_FIELD, Column, Diagnostic, End, Relationship, Schema, Table

SECTIONS = ["tables", "settings", "layout"]
SECTION_ALIASES = {"rels": "relationships"}
ALLOWED_REL = ", ".join(REL_TYPES)
REJECT = "QuickDBD would reject this: "

# qdbd directives live in comments, so files stay valid QuickDBD.
TAG_RE = re.compile(r"^@(tags?|dbt-tags?)\s*:?\s*(.*)$", re.I)
COLOR_RE = re.compile(r"^@colou?r\b\s*:?\s*(.*)$", re.I)
TAG_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
HEX_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


def split_tags(text: str) -> list[str]:
    out: list[str] = []
    for t in re.split(r"[\s,]+", text.strip()):
        t = t.lower()
        if t and t not in out:
            out.append(t)
    return out


# --------------------------------------------------------------------------- helpers


def _allowed_char(ch: str) -> bool:
    return bool(re.match(r"[a-zA-Z0-9_]", ch))


def encode(text: str) -> str:
    """QuickDBD's identifier encoding: non [A-Za-z0-9_] characters become their char code."""
    return "".join(ch if _allowed_char(ch) else str(ord(ch)) for ch in text)


def _is_same_chars(value: str, ch: str) -> bool:
    return value.startswith(ch) and (value == ch or re.fullmatch(r"(.)\1+", value, re.S) is not None)


def is_separator(value: str) -> bool:
    return _is_same_chars(value, "-")


def is_virtual(name: str) -> bool:
    return _is_same_chars(name, ".")


def is_rel_type(token: str | None) -> bool:
    return token is not None and token.strip() in REL_TYPES


def _split_ws(text: str) -> list[str]:
    return [t for t in text.split(" ") if t] if text else []


def _is_numeric(text: str) -> bool:
    try:
        v = float(text.strip())
    except (ValueError, AttributeError):
        return False
    return v == v and v not in (float("inf"), float("-inf"))


_LEADING_FLOAT = re.compile(r"^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


def _parse_float(text: str) -> float | None:
    m = _LEADING_FLOAT.match(text)
    return float(m.group(0)) if m else None


def _split_first(text: str, delim: str) -> list[str]:
    i = text.find(delim)
    if i == -1:
        return [text]
    return [text[:i], text[i + 1 :]]


def line_data(raw: str) -> tuple[str, str | None]:
    """Split a raw line into (data, comment). ``#`` inside double quotes is not a comment."""
    if "#" not in raw:
        return raw.rstrip(), None
    parts = raw.split("#")
    found = False
    data = ""
    comment = ""
    for part in parts:
        if found:
            comment = part
            break
        joined = (data + "#" if data else "") + part
        data = joined
        if joined.count('"') % 2 == 0:
            found = True
    return data.rstrip(), comment.strip()


@dataclass
class Token:
    value: str
    encoded: str | None = None


def tokenize_field_line(text: str) -> list[Token]:
    if '"' not in text:
        return [Token(t) for t in _split_ws(text)]
    state = 0 if text.startswith('"') else 1
    tokens: list[Token] = []
    raw: list[str] = []
    enc: list[str] = []

    def push() -> None:
        v, e = "".join(raw), "".join(enc)
        tokens.append(Token(v, e if e != v else None))

    for ch in text[1 if state == 0 else 0 :]:
        if state == 0:
            if ch == '"':
                state = 1
            else:
                raw.append(ch)
                enc.append(ch)
        elif state == 1:
            if ch == " ":
                if raw:
                    push()
                    raw, enc = [], []
            elif ch == '"':
                state = 2
            else:
                raw.append(ch)
                enc.append(ch)
        else:
            if ch == '"':
                state = 1
            else:
                raw.append(ch)
                enc.append(ch if _allowed_char(ch) else str(ord(ch)))
    if raw:
        push()
    return tokens


def tokenize_layout_line(text: str) -> list[str]:
    if '"' not in text:
        return _split_ws(text)
    state = 0 if text.startswith('"') else 1
    out: list[str] = []
    cur: list[str] = []
    for ch in text[1 if state == 0 else 0 :]:
        if state == 0:
            if ch == '"':
                state = 1
            else:
                cur.append(ch)
        else:
            if ch == " ":
                if cur:
                    out.append("".join(cur))
                    cur = []
            else:
                cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


# --------------------------------------------------------------------------- per-file parsing


@dataclass
class Entry:
    line: int
    value: str
    comments: list[str]


@dataclass
class PendingRel:
    member1: str
    rel_type: str
    member2: str
    path: str
    line: int
    case_sensitive: bool
    cards: tuple[str, str] | None = None  # DBML: each end's cardinality (its operators go beyond REL_TYPES)


@dataclass
class FileParse:
    path: str
    syntax: str = "quickdbd"  # or "dbml"
    tables: dict[str, Table] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    rels: list[PendingRel] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    layout_entries: list[Entry] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    general_comments: list[str] = field(default_factory=list)
    colors: dict[str, tuple[str, int]] = field(default_factory=dict)  # tag -> (#hex, line)
    unmodelled: list[tuple[int, str]] = field(default_factory=list)  # DBML: (line, what) parsed, not drawn
    enums: dict[str, list[str]] = field(default_factory=dict)  # DBML: enum name -> values
    groups: dict[str, int] = field(default_factory=dict)  # DBML: TableGroup name -> line

    def error(self, line: int, msg: str) -> None:
        self.diagnostics.append(Diagnostic(self.path, line, msg, "error"))

    def warn(self, line: int, msg: str) -> None:
        self.diagnostics.append(Diagnostic(self.path, line, REJECT + msg, "warning"))


class _FileParser:
    def __init__(self, text: str, path: str):
        self.text = text
        self.fp = FileParse(path)

    # -- sectioning ---------------------------------------------------------
    def tokenize(self) -> dict[str, list[Entry]]:
        fp = self.fp
        out: dict[str, list[Entry]] = {"settings": [], "tables": [], "layout": []}
        pending: list[str] = []
        section = "tables"
        seen_sections: list[str] = []
        seen_data = False
        for idx, raw in enumerate(re.split(r"\r?\n", self.text)):
            lineno = idx + 1
            if "\t" in raw:
                data_part, _ = line_data(raw)
                if "\t" in data_part:
                    fp.warn(lineno, "tab character found (QuickDBD expects spaces)")
                raw = raw.replace("\t", " ")
            blank = raw.rstrip() == ""
            data, comment = line_data(raw)
            if comment and COLOR_RE.match(comment):
                # the hex value has its own '#', which line_data treats as the end of the comment
                full = re.search(r"#\s*(@colou?r\b.*)$", raw, re.I)
                self._color(full.group(1).strip() if full else comment, lineno)
                comment = None
            if comment:
                pending.append(comment)
            elif blank and not seen_data:
                fp.general_comments.extend(pending)
                pending = []
            if data:
                seen_data = True
            if (blank and section != "tables") or (not blank and not data):
                continue
            entry = Entry(lineno, data, pending if (seen_data and data) else [])
            if seen_data and data:
                pending = []
            if data.startswith("[") and data.endswith("]"):
                name = data.rstrip("]").lstrip("[").lower()
                name = SECTION_ALIASES.get(name, name)
                if not self._validate_section(name, seen_sections, lineno):
                    continue
                seen_sections.append(name)
                section = name
            else:
                out[section].append(entry)
        return out

    def _color(self, comment: str, line: int) -> None:
        parts = COLOR_RE.match(comment).group(1).split()
        if len(parts) > 2 and parts[2].startswith("#"):  # a trailing comment after the colour
            parts = parts[:2]
        if len(parts) != 2 or not TAG_NAME_RE.match(parts[0]) or not HEX_RE.match(parts[1]):
            self.fp.diagnostics.append(
                Diagnostic(self.fp.path, line, "Invalid @color directive (use '# @color TAG #rrggbb')", "warning")
            )
            return
        self.fp.colors[parts[0].lower()] = (parts[1].lower(), line)

    def _validate_section(self, name: str, seen: list[str], line: int) -> bool:
        if name not in SECTIONS:
            self.fp.error(line, f"Invalid section name '[{name}]' (allowed: {', '.join(SECTIONS)})")
            return False
        if name in seen:
            self.fp.error(line, f"Section '[{name}]' is already defined")
            return False
        before = SECTIONS[: SECTIONS.index(name)]
        later = [s for s in seen if s not in before]
        if later:
            self.fp.error(
                line, f"Section '[{name}]' is out of order. It must be defined before: '[{', '.join(later)}]'"
            )
            return False
        return True

    # -- settings -----------------------------------------------------------
    def parse_settings(self, entries: list[Entry]) -> None:
        fp = self.fp
        s = fp.settings
        for e in entries:
            parts = _split_first(e.value, " ")
            key = parts[0].strip()
            k = key.lower()
            val = parts[1].strip() if len(parts) > 1 else ""
            if not k:
                fp.error(e.line, "Setting key missing")
            elif " " in k:
                fp.error(e.line, "Setting key cannot contain whitespace")
            elif not val:
                fp.error(e.line, "Setting value missing")
            elif k in s:
                fp.error(e.line, f"Setting '{key}' already defined")
            else:
                parsed: object = val
                if k in ("casesensitive", "casesensitivity"):
                    k = "casesensitive"
                    if val.lower() == "off":
                        parsed = False
                    elif val.lower() == "on":
                        parsed = True
                    else:
                        parsed = None
                        fp.error(e.line, "Invalid 'CaseSensitive' value (allowed: 'on', 'off')")
                elif k == "position":
                    parsed = self._parse_position(val, e.line)
                elif k == "zoom":
                    z = _parse_float(val)
                    if z is None or z < 10 or z > 200:
                        fp.error(e.line, "Invalid 'Zoom' value (allowed: number between 10 and 200)")
                    parsed = z
                s[k] = parsed
                s.setdefault("_lines", {})[k] = e.line
        if not isinstance(s.get("casesensitive"), bool):
            s["casesensitive"] = False

    def _parse_position(self, val: str, line: int):
        parts = _split_first(val, " ")
        if len(parts) != 2:
            self.fp.error(line, "Position setting requires 2 values (x, y)")
            return None
        x, y = parts[0].strip(), parts[1].strip()
        if not _is_numeric(x):
            self.fp.error(line, f"Invalid X coordinate '{x or 'undefined'}', number expected")
            return None
        if not _is_numeric(y):
            self.fp.error(line, f"Invalid Y coordinate '{y or 'undefined'}', number expected")
            return None
        return (float(int(float(x))), float(int(float(y))))

    # -- tables -------------------------------------------------------------
    def parse_tables(self, entries: list[Entry]) -> None:
        groups: list[list[Entry]] = []
        cur: list[Entry] = []
        for e in entries:
            if e.value == "":
                if cur:
                    groups.append(cur)
                cur = []
            else:
                cur.append(e)
        if cur:
            groups.append(cur)
        for g in groups:
            self._parse_table(g)

    def _parse_table(self, group: list[Entry]) -> None:
        fp = self.fp
        table_id: str | None = None
        after_sep = False
        for idx, e in enumerate(group):
            value = e.value
            if value != value.lstrip() and (idx == 0 or is_separator(value.strip())):
                fp.warn(e.line, "indented table name or separator")
                value = value.strip()
            if is_separator(value):
                if idx == 0:
                    fp.error(e.line, "Table name not defined")
                after_sep = True
                continue
            if idx == 0:
                table_id = self._parse_table_name(Entry(e.line, value, e.comments))
            elif table_id:
                if after_sep:
                    self._set_field(table_id, self._parse_field(table_id, e), e.line)
                else:
                    self._parse_metadata(table_id, e)

    def _parse_table_name(self, e: Entry) -> str | None:
        fp = self.fp
        parts = e.value.split(" as ")
        name = parts[0]
        if '"' in name or (" " not in name and "." not in name):
            aliases = parts[1].replace(" ", "").split(",") if len(parts) > 1 else []
            caption = name.strip('"')
            ident = encode(caption)
            if ident in fp.tables:
                fp.error(e.line, f"Table '{caption}' already defined")
                return None
            table = Table(ident, caption, fp.path, e.line, aliases, {})
            for c in e.comments:
                m = TAG_RE.match(c)
                if not m:
                    table.comments.append(c)
                elif m.group(1).lower().startswith("dbt"):
                    table.dbt_tags += [t for t in split_tags(m.group(2)) if t not in table.dbt_tags]
                else:
                    table.tags += [t for t in split_tags(m.group(2)) if t not in table.tags]
            fp.tables[ident] = table
            for a in aliases:
                fp.aliases[a] = ident
            return ident
        fp.error(e.line, "Invalid table name (use double quotes)")
        return None

    def _parse_metadata(self, table_id: str, e: Entry) -> None:
        if e.value.startswith("rel"):
            parts = _split_ws(e.value)
            if len(parts) > 3:
                self.fp.error(e.line, f"Unknown relationship param '{parts[3]}'")
                return
            rel_type = parts[1] if len(parts) == 3 else "-"
            target = parts[2] if len(parts) == 3 else (parts[1] if len(parts) > 1 else "")
            self._queue(table_id, rel_type, target, e.line)
        else:
            self.fp.error(e.line, f"Unrecognized table metadata '{e.value}'")

    def _queue(self, m1: str, rel_type: str, m2: str, line: int) -> None:
        self.fp.rels.append(PendingRel(m1, rel_type, m2, self.fp.path, line, False))

    def _merge_paren_tokens(self, tokens: list[Token], line: int) -> list[Token]:
        """Forgiving: `decimal(10, 2)` -> one token `decimal(10,2)`."""
        out: list[Token] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            depth = t.value.count("(") - t.value.count(")")
            if depth > 0 and t.encoded is None and i + 1 < len(tokens):
                j = i
                value = t.value
                while depth > 0 and j + 1 < len(tokens) and tokens[j + 1].encoded is None:
                    j += 1
                    value += tokens[j].value
                    depth += tokens[j].value.count("(") - tokens[j].value.count(")")
                if depth == 0 and j > i:
                    self.fp.warn(line, f"spaces inside '{' '.join(x.value for x in tokens[i : j + 1])}'")
                    out.append(Token(value))
                    i = j + 1
                    continue
            out.append(t)
            i += 1
        return out

    def _parse_field(self, table_id: str, e: Entry) -> Column | None:
        fp = self.fp
        tokens = tokenize_field_line(e.value)
        if not tokens:
            fp.error(e.line, "Table field name cannot be empty")
            return None
        name = tokens[0].value.strip()
        ident = encode(name)
        if not ident:
            fp.error(e.line, "Table field name cannot be empty")
            return None
        if is_virtual(ident):
            return Column(VIRTUAL_FIELD, "", e.line, virtual=True)
        tokens = [tokens[0]] + self._merge_paren_tokens(tokens[1:], e.line)
        col = Column(ident, name, e.line, comments=list(e.comments))
        fk_at = -1
        d = 0
        while d + 1 < len(tokens):
            d += 1
            c = tokens[d]
            low = c.value.strip()
            if fk_at > -1:
                if d == fk_at + 1:
                    if is_rel_type(c.value):
                        if d == len(tokens) - 1:
                            fp.error(e.line, "Relationship key cannot be empty")
                        continue
                    fk_at = -1
                elif d == fk_at + 2:
                    self._queue(f"{table_id}.{ident}", tokens[d - 1].value or "-", c.encoded or c.value or "", e.line)
                    fk_at = -1
                    continue
            h = low.lower()
            if h == "not" and d + 1 < len(tokens) and tokens[d + 1].value.strip().lower() == "null":
                fp.warn(e.line, "explicit 'NOT NULL' (columns are NOT NULL by default)")
                d += 1
                continue
            if h in ("null", "nullable"):
                col.nullable = True
            elif h == "pk":
                if col.unique:
                    fp.error(
                        e.line, "The field cannot be a primary key and an unique key, since a primary key is unique"
                    )
                if col.index:
                    fp.error(e.line, "The field cannot be a primary key and an index, since a primary key is an index")
                col.pk = True
            elif h == "unique":
                if col.pk:
                    fp.error(
                        e.line, "The field cannot be a primary key and an unique key, since a primary key is unique"
                    )
                if col.index:
                    fp.error(e.line, "The field cannot be an unique key and an index, since an unique key is an index")
                col.unique = True
            elif h == "index":
                if col.pk:
                    fp.error(e.line, "The field cannot be a primary key and an index, since a primary key is an index")
                if col.unique:
                    fp.error(e.line, "The field cannot be an unique key and an index, since an unique key is an index")
                col.index = True
            elif h == "fk":
                col.fk = True
                fk_at = d
            elif h in ("identity", "autoincrement"):
                col.identity = True
            elif h.startswith("default="):
                col.default = low[len("default=") :]
            elif col.type is not None:
                fp.error(e.line, f"Unrecognized keyword '{low}'")
            elif "=" in low:
                parts = low.split("=")
                col.type, col.default = parts[0], parts[1]
            else:
                col.type = low
        return col

    def _set_field(self, table_id: str, col: Column | None, line: int) -> None:
        if col is None:
            return
        table = self.fp.tables[table_id]
        if col.id in table.columns:
            self.fp.error(line, f"Table field '{col.id}' already defined")
            return
        col.order = len(table.columns)
        table.columns[col.id] = col

    def run(self) -> FileParse:
        sections = self.tokenize()
        self.parse_settings(sections["settings"])
        cs = self.fp.settings["casesensitive"]
        default_type = self.fp.settings.get("defaultfieldtype")
        self.parse_tables(sections["tables"])
        for r in self.fp.rels:
            r.case_sensitive = cs
        if default_type:
            for t in self.fp.tables.values():
                for c in t.columns.values():
                    if c.type is None and not c.virtual:
                        c.type = default_type
        self.fp.layout_entries = sections["layout"]
        return self.fp


# A DBML top-level declaration. No valid QuickDBD file has one: a QuickDBD table header can't hold `{`, and a
# column line can't start with a keyword followed by a name and `{`, or be a `Ref:` with a relationship operator.
_DBML_BLOCK = re.compile(
    r"^\s*(table|enum|tablegroup|tablepartial|records)\s+(\"[^\"]*\"|[\w.]+)[^{]*\{\s*(//.*)?$", re.I
)
_DBML_PROJECT = re.compile(r"^\s*project\b[^{]*\{\s*(//.*)?$", re.I)
_DBML_REF = re.compile(
    r"^\s*ref(\s+(\"[^\"]*\"|\w+))?\s*(\{\s*(//.*)?$|:\s*[\w\"]+[\w\".()\s,]*?\s*\??(<>|<|>|-)\??\s*[\w\"])", re.I
)


def syntax_of(path: str, text: str) -> str:
    """ "dbml" for a .dbml file, or any file with a DBML top-level declaration; else "quickdbd"."""
    if path.lower().endswith(".dbml"):
        return "dbml"
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for line in text.splitlines():
        if _DBML_BLOCK.match(line) or _DBML_PROJECT.match(line) or _DBML_REF.match(line):
            return "dbml"
    return "quickdbd"


def parse_file(text: str, path: str = "<input>") -> FileParse:
    if syntax_of(path, text) == "dbml":
        from .dbml import parse_dbml

        return parse_dbml(text, path)
    return _FileParser(text, path).run()


# --------------------------------------------------------------------------- whole-schema compile


class _Resolver:
    def __init__(self, files: list[FileParse]):
        self.files = files
        self.schema = Schema()
        self.aliases: dict[str, str] = {}
        self._diag: dict[str, list[Diagnostic]] = {f.path: f.diagnostics for f in files}

    def error(self, path: str, line: int, msg: str, severity: str = "error") -> None:
        self._diag.setdefault(path, []).append(Diagnostic(path, line, msg, severity))

    def get_table(self, ident: str, cs: bool) -> Table | None:
        if cs:
            return self.schema.tables.get(ident)
        low = ident.lower()
        for t in self.schema.tables.values():
            if t.id.lower() == low:
                return t
        return None

    @staticmethod
    def get_column(table: Table, ident: str, cs: bool) -> Column | None:
        if cs:
            return table.columns.get(ident)
        low = ident.lower()
        for c in table.columns.values():
            if c.id.lower() == low:
                return c
        return None

    def merge(self) -> None:
        s = self.schema
        for f in self.files:
            for ident, table in f.tables.items():
                if ident in s.tables:
                    first = s.tables[ident]
                    self.error(
                        f.path,
                        table.line,
                        f"Table '{table.name}' already defined (first defined at {first.path}:{first.line})",
                    )
                    continue
                s.tables[ident] = table
            self.aliases.update(f.aliases)
            s.general_comments.extend(f.general_comments)
            for tag, (color, line) in sorted(f.colors.items()):
                if tag not in s.tag_colors:
                    s.tag_colors[tag] = color
                elif s.tag_colors[tag] != color:
                    msg = f"@color for '{tag}' differs from an earlier file; using the first"
                    self.error(f.path, line, msg, "warning")
            zoom = f.settings.get("zoom")
            pos = f.settings.get("position")
            lines = f.settings.get("_lines", {})
            if zoom is not None:
                if s.zoom is None:
                    s.zoom = zoom
                elif s.zoom != zoom:
                    self.error(f.path, lines["zoom"], "Zoom differs from an earlier file; using the first", "warning")
            if pos is not None:
                if s.position is None:
                    s.position = pos
                elif s.position != pos:
                    self.error(
                        f.path, lines["position"], "Position differs from an earlier file; using the first", "warning"
                    )

    def parse_token(self, text: str, rel: PendingRel) -> End | None:
        t = text.strip()
        if not t:
            self.error(rel.path, rel.line, "Relationship key cannot be empty")
            return None
        parts = t.split(".")
        if len(parts) > 2:
            self.error(rel.path, rel.line, "Multi-nested relationships are not allowed")
            return None
        table = self.get_table(parts[0], rel.case_sensitive)
        col = self.get_column(table, parts[1], rel.case_sensitive) if (len(parts) == 2 and table) else None
        table_id = table.id if table else parts[0]
        col_id = (col.id if col else parts[1]) if len(parts) == 2 else VIRTUAL_FIELD
        return End(table_id, col_id)

    def resolve_rels(self) -> None:
        s = self.schema
        for rel in (r for f in self.files for r in f.rels):
            if rel.cards is None and not is_rel_type(rel.rel_type):
                self.error(rel.path, rel.line, f"Invalid relationship description (allowed: {ALLOWED_REL})")
                continue
            a = self.parse_token(rel.member1, rel)
            b = self.parse_token(rel.member2, rel)
            if not (a and b):
                continue
            for end in (a, b):
                if end.table in self.aliases:
                    end.table = self.aliases[end.table]
                t = self.get_table(end.table, rel.case_sensitive)
                if t:
                    end.table = t.id
            a.card, b.card = rel.cards or REL_TYPES[rel.rel_type.strip()]
            dup = next((r for r in s.relationships if _same_rel(r, a, b)), None)
            if dup:
                where = f"{dup.line}" if dup.path == rel.path else f"{dup.path}:{dup.line}"
                self.error(rel.path, rel.line, f"Relationship already defined at line {where}")
                continue
            r = Relationship(a, b, rel.path, rel.line)
            s.relationships.append(r)
            self.post_process(r, rel.case_sensitive)

    def post_process(self, r: Relationship, cs: bool) -> None:
        tables = []
        for end in (r.a, r.b):
            t = self.get_table(end.table, cs)
            if t is None:
                self.error(r.path, r.line, f"Invalid relationship, the table '{end.table}' does not exist")
            tables.append(t)
        if None in tables:
            return
        cols = []
        for end, t in zip((r.a, r.b), tables, strict=True):
            if not end.column:
                self.error(r.path, r.line, f"Invalid relationship, the field '{end.table}.' is missing.")
                cols.append(None)
                continue
            c = self.get_column(t, end.column, cs)
            if c is None:
                if end.column != VIRTUAL_FIELD:
                    self.error(
                        r.path, r.line, f"Invalid relationship, the field '{end.table}.{end.column}' does not exist"
                    )
                    cols.append(None)
                    continue
                c = Column(VIRTUAL_FIELD, "", r.line, order=len(t.columns), virtual=True)
                t.columns[VIRTUAL_FIELD] = c
            end.column = c.id
            cols.append(c)
        for c in cols:
            if c is not None and not c.pk and not c.virtual:
                c.fk = True

    def parse_layout(self) -> None:
        s = self.schema
        for f in self.files:
            cs = f.settings["casesensitive"]
            for e in f.layout_entries:
                parts = tokenize_layout_line(e.value)
                if len(parts) != 3:
                    self.error(f.path, e.line, "Layout definition requires 3 values (tableName, x, y)")
                    continue
                name, xs, ys = parts
                ident = encode(name)
                if not ident:
                    self.error(f.path, e.line, "Table name cannot be empty")
                    continue
                t = self.get_table(ident, cs)
                if t is None:
                    self.error(
                        f.path,
                        e.line,
                        REJECT + f"Invalid layout definition name, the table '{name}' does not exist",
                        "warning",
                    )
                    continue
                if t.id in s.layout:
                    self.error(f.path, e.line, f"Layout for '{name}' already defined")
                    continue
                if not _is_numeric(xs):
                    self.error(f.path, e.line, f"Invalid X coordinate '{xs.strip()}', number expected")
                    continue
                if not _is_numeric(ys):
                    self.error(f.path, e.line, f"Invalid Y coordinate '{ys.strip()}', number expected")
                    continue
                s.layout[t.id] = (float(xs), float(ys))

    def run(self) -> Schema:
        self.merge()
        self.resolve_rels()
        self.parse_layout()
        diags = [d for f in self.files for d in self._diag.get(f.path, [])]
        order = {f.path: i for i, f in enumerate(self.files)}
        diags.sort(key=lambda d: (order.get(d.path, 0), d.line))
        self.schema.diagnostics = diags
        return self.schema


def _same_rel(r: Relationship, a: End, b: End) -> bool:
    return (r.a.table == a.table and r.a.column == a.column and r.b.table == b.table and r.b.column == b.column) or (
        r.a.table == b.table and r.a.column == b.column and r.b.table == a.table and r.b.column == a.column
    )


def compile_files(sources: list[tuple[str, str]]) -> tuple[Schema, list[FileParse]]:
    """Like ``compile_sources``, also returning each file's own parse (comments, settings, DBML extras)."""
    files = [parse_file(text, path) for path, text in sources]
    return _Resolver(files).run(), files


def compile_sources(sources: list[tuple[str, str]]) -> Schema:
    """Compile ``[(path, text), ...]`` into one Schema (tables share one namespace)."""
    return compile_files(sources)[0]


def compile_text(text: str, path: str = "<input>") -> Schema:
    return compile_sources([(path, text)])
