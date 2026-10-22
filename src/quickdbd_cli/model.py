"""Data model shared by the parser, layout, and renderers."""

from __future__ import annotations

from dataclasses import dataclass, field

VIRTUAL_FIELD = "qdbdvirtualfield"

# Relationship operator -> (cardinality of left member, cardinality of right member)
REL_TYPES: dict[str, tuple[str, str]] = {
    "-": ("one", "one"),
    "-<": ("one", "many"),
    ">-": ("many", "one"),
    ">-<": ("many", "many"),
    "-0": ("one", "zeroOne"),
    "0-": ("zeroOne", "one"),
    "0-0": ("zeroOne", "zeroOne"),
    "-0<": ("one", "zeroMany"),
    ">0-": ("zeroMany", "one"),
}


@dataclass
class Diagnostic:
    path: str
    line: int
    message: str
    severity: str = "error"  # "error" | "warning"

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.severity}: {self.message}"


@dataclass
class Column:
    id: str
    name: str
    line: int
    order: int = 0
    type: str | None = None
    pk: bool = False
    fk: bool = False
    nullable: bool = False
    unique: bool = False
    index: bool = False
    identity: bool = False
    default: str | None = None
    virtual: bool = False
    comments: list[str] = field(default_factory=list)


@dataclass
class Table:
    id: str
    name: str
    path: str
    line: int
    aliases: list[str] = field(default_factory=list)
    columns: dict[str, Column] = field(default_factory=dict)
    comments: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # `# @tag: ...` comments
    dbt_tags: list[str] = field(default_factory=list)  # `# @dbt-tags: ...`, written by `qdbd import dbt`
    group: str | None = None  # DBML TableGroup; else the explorer groups by file
    color: str | None = None  # DBML headercolor; beats tag colours
    end_line: int | None = None  # DBML: the closing `}` line


@dataclass
class End:
    table: str
    column: str  # column id, or VIRTUAL_FIELD for a table-level relationship
    card: str = "one"


@dataclass
class Relationship:
    a: End
    b: End
    path: str
    line: int


@dataclass
class Schema:
    tables: dict[str, Table] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    zoom: float | None = None
    position: tuple[float, float] | None = None
    layout: dict[str, tuple[float, float]] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    general_comments: list[str] = field(default_factory=list)
    tag_colors: dict[str, str] = field(default_factory=dict)  # `# @color TAG #hex`

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    def valid_relationships(self) -> list[Relationship]:
        """Relationships whose both ends resolve to existing tables/columns."""
        out = []
        for rel in self.relationships:
            ok = True
            for end in (rel.a, rel.b):
                t = self.tables.get(end.table)
                if t is None or end.column not in t.columns:
                    ok = False
            if ok:
                out.append(rel)
        return out
