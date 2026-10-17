"""`qdbd` command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .model import Schema
from .project import Project, SelectionError, selector_expr

OK = "No errors found. Good job!"


def _print_diagnostics(schema: Schema, strict: bool) -> bool:
    """Print diagnostics; returns True when the schema is usable."""
    for d in schema.diagnostics:
        print(d.format(), file=sys.stderr)
    failed = bool(schema.errors) or (strict and bool(schema.warnings))
    if failed:
        n_e, n_w = len(schema.errors), len(schema.warnings)
        print(f"{n_e} error(s), {n_w} warning(s)", file=sys.stderr)
    return not failed


def _open(args) -> Project:
    return Project.open([Path(p) for p in args.paths], Path(args.layout) if getattr(args, "layout", None) else None)


def _title(project: Project) -> str:
    if len(project.inputs) == 1:
        p = project.inputs[0]
        return p.stem if p.is_file() else (p.resolve().name or "diagram")
    return "diagram"


def cmd_check(args) -> int:
    project = _open(args)
    schema = project.compile()
    ok = _print_diagnostics(schema, args.strict)
    if ok and not schema.diagnostics:
        print(OK)
    elif ok:
        print(f"No errors found ({len(schema.warnings)} warning(s)).")
    return 0 if ok else 1


def cmd_build(args) -> int:
    from .html import render_page

    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, args.strict):
        return 1
    try:
        model, pos = project.build(schema, select=selector_expr(args.select, args.exclude))
    except SelectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_page(model, pos, _title(project)), encoding="utf-8")
    print(f"Wrote {out} ({len(model['tables'])} tables, {len(model['rels'])} relationships)")
    return 0


def cmd_export(args) -> int:
    from . import export

    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, args.strict):
        return 1
    try:
        model, pos = project.build(schema, select=selector_expr(args.select, args.exclude))
    except SelectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    only = None
    if not args.focus and (args.select or args.exclude):
        only = [t["id"] for t in model["tables"]]
        pos = export.focus_positions(model, pos, only)  # compact layout for the selection
    if args.focus:
        t = export.find_table(model, args.focus)
        if t is None:
            print(f"error: table '{args.focus}' not found", file=sys.stderr)
            return 1
        only = export.focus_ids(model, t["id"], args.depth)
        pos = export.focus_positions(model, pos, only)
    out = Path(args.output)
    fmt = out.suffix.lower().lstrip(".")
    if fmt not in ("svg", "png"):
        print("error: output must end in .svg or .png", file=sys.stderr)
        return 2
    svg = export.render_svg(model, pos, only=only, mode=args.mode, embed_font=(fmt == "svg"))
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "svg":
        out.write_text(svg, encoding="utf-8")
    else:
        out.write_bytes(export.svg_to_png(svg, args.scale))
    print(f"Wrote {out} ({len(only) if only else len(model['tables'])} tables)")
    return 0


def cmd_layout(args) -> int:
    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, False):
        return 1
    model, pos = project.build(schema, reset=args.reset)
    project.save_positions(model, pos)
    print(f"Wrote {project.sidecar} ({len(pos)} tables)")
    return 0


def cmd_import_dbt(args) -> int:
    from .dbt import DbtImportError, import_dbt, write_result
    from .parser import compile_sources

    out = Path(args.output)
    split = out.suffix != ".txt"
    try:
        result = import_dbt(
            Path(args.manifest),
            Path(args.catalog) if args.catalog else None,
            packages=args.package,
            select=args.select,
            sources=not args.no_sources,
            split=split,
        )
    except DbtImportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    # Self-check: the generated text must compile cleanly.
    schema = compile_sources([(name, text) for name, text in result.files.items()])
    if schema.errors:
        for d in schema.errors:
            print(d.format(), file=sys.stderr)
        print("error: generated schema did not compile (please report this as a bug)", file=sys.stderr)
        return 1
    written = write_result(result, out)
    for s in result.skipped:
        print(f"skipped: {s}", file=sys.stderr)
    where = str(out) if not split else f"{out}/ ({len(written)} files)"
    print(f"Wrote {where}: {result.tables} tables, {result.relationships} relationships")
    if result.tables and not result.relationships:
        print(
            "hint: no relationships found; add `relationships` tests or foreign_key constraints in dbt", file=sys.stderr
        )
    return 0


def cmd_serve(args) -> int:
    from .serve import serve

    project = _open(args)
    return serve(project, port=args.port, open_browser=not args.no_open)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qdbd", description="Compile QuickDBD schema files into interactive ER diagrams.")
    p.add_argument("--version", action="version", version=f"qdbd {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def paths(sp):
        sp.add_argument("paths", nargs="+", metavar="PATH", help="schema .txt file(s) or folder(s) (recursive)")

    def selectors(sp):
        sp.add_argument(
            "-s",
            "--select",
            action="append",
            metavar="SELECTOR",
            help="dbt-style: name glob, +name (and what it references), name+ (and what references it), "
            "N+name+N (hops), group:/file:/col: methods, a,b intersects (repeatable)",
        )
        sp.add_argument("--exclude", action="append", metavar="SELECTOR", help="drop tables matching (repeatable)")

    sp = sub.add_parser("check", help="validate schema files")
    paths(sp)
    sp.add_argument("--strict", action="store_true", help="treat warnings (QuickDBD incompatibilities) as errors")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("build", help="write an interactive HTML diagram")
    paths(sp)
    sp.add_argument("-o", "--output", default="diagram.html")
    selectors(sp)
    sp.add_argument("--layout", help="layout sidecar file (default: next to the schema)")
    sp.add_argument("--strict", action="store_true")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("export", help="write a PNG or SVG image")
    paths(sp)
    sp.add_argument("-o", "--output", required=True, help="out.png or out.svg")
    selectors(sp)
    sp.add_argument("--focus", metavar="TABLE", help="only this table and its neighbours")
    sp.add_argument("--depth", type=int, default=1, help="relationship hops around --focus (default 1)")
    sp.add_argument("--mode", choices=["full", "keys", "header"], default="full", help="collapse mode")
    sp.add_argument("--scale", type=float, default=2.0, help="PNG pixel scale (default 2)")
    sp.add_argument("--layout")
    sp.add_argument("--strict", action="store_true")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("layout", help="write table positions to the layout sidecar")
    paths(sp)
    sp.add_argument("--reset", action="store_true", help="discard saved positions and auto-layout everything")
    sp.add_argument("--layout")
    sp.set_defaults(func=cmd_layout)

    sp = sub.add_parser("import", help="generate QuickDBD schema files from another source")
    isub = sp.add_subparsers(dest="source", required=True)
    dp = isub.add_parser(
        "dbt",
        help="from a dbt project's target/manifest.json",
        description="Tables from models/seeds/snapshots/sources, relationships from `relationships` tests and "
        "foreign_key constraints, types from catalog.json (run `dbt docs generate` first for types).",
    )
    dp.add_argument("manifest", help="path to manifest.json (or the target/ directory)")
    dp.add_argument("-o", "--output", default="schema.txt", help="a .txt file, or a directory for one file per folder")
    dp.add_argument("--catalog", help="catalog.json for column types (default: next to the manifest, if present)")
    dp.add_argument(
        "--package",
        action="append",
        help="dbt package(s) to include (default: the root project; 'all' for every package)",
    )
    dp.add_argument(
        "--select", action="append", help="glob on model name, fqn (a.b.c) or file path, e.g. 'marts.*' (repeatable)"
    )
    dp.add_argument("--no-sources", action="store_true", help="leave out dbt sources")
    dp.set_defaults(func=cmd_import_dbt)

    sp = sub.add_parser("serve", help="live editor: reload on save, drag tables to arrange")
    paths(sp)
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--layout")
    sp.add_argument("--no-open", action="store_true", help="don't open a browser")
    sp.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
