"""`qdbd` command line."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

from . import __version__
from .model import Diagnostic, Schema
from .project import Project, SelectionError, selector_expr

OK = "No errors found. Good job!"
BY_GROUP_HELP = "fresh layout that keeps each file / dbt folder together, with regions (ignores saved positions)"


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


def _github_annotation(d: Diagnostic, level: str) -> str:
    """A GitHub Actions workflow command, which shows `d` inline on the PR's changed lines."""

    def esc(s: str) -> str:
        return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    def esc_prop(s: str) -> str:
        return esc(s).replace(":", "%3A").replace(",", "%2C")

    return f"::{level} file={esc_prop(d.path)},line={d.line},title=qdbd::{esc(d.message)}"


def _symbols(schema: Schema) -> dict:
    """Tables, columns and relationships with their source lines, for editor outlines, go-to-definition and the
    VS Code sidebar (column types and keys, table docs)."""
    tables = []
    for t in schema.tables.values():
        cols = [
            {"name": c.name, "line": c.line, "type": c.type, "pk": c.pk, "fk": c.fk}
            for c in t.columns.values()
            if not c.virtual
        ]
        end = t.end_line or max([t.line + 1] + [c["line"] for c in cols])
        table = {"name": t.name, "aliases": t.aliases, "file": t.path, "line": t.line, "endLine": end, "columns": cols}
        if t.comments:
            table["doc"] = "\n".join(t.comments)
        tables.append(table)

    def end(e) -> dict:
        t = schema.tables.get(e.table)
        c = t.columns.get(e.column) if t else None
        return {"table": t.name if t else e.table, "column": c.name if c and not c.virtual else None}

    rels = [{"file": r.path, "line": r.line, "a": end(r.a), "b": end(r.b)} for r in schema.relationships]
    return {"tables": tables, "rels": rels}


def cmd_check(args) -> int:
    project = _open(args)
    overrides = None
    if args.stdin_file:
        target = Path(args.stdin_file).resolve()
        if target not in {f.resolve() for f in project.files}:
            print(f"error: --stdin-file {args.stdin_file} is not one of the schema files", file=sys.stderr)
            return 2
        overrides = {target: sys.stdin.read()}
    schema = project.compile(overrides)
    if args.format == "json":
        ok = not schema.errors and not (args.strict and schema.warnings)
        diags = [dataclasses.asdict(d) for d in schema.diagnostics]
        report = {"ok": ok, "errors": len(schema.errors), "warnings": len(schema.warnings), "diagnostics": diags}
        if args.symbols:
            report.update(_symbols(schema))
        print(json.dumps(report, indent=2))
        return 0 if ok else 1
    if args.format == "github":
        # Under --strict a warning fails the job, so it's annotated as an error.
        for d in schema.diagnostics:
            print(_github_annotation(d, "error" if args.strict else d.severity))
    ok = _print_diagnostics(schema, args.strict)
    if ok and not schema.diagnostics:
        print(OK)
    elif ok:
        print(f"No errors found ({len(schema.warnings)} warning(s)).")
    return 0 if ok else 1


def _built_page(args) -> tuple[str, dict] | int:
    """Compile, select and lay out like `build`; returns (html, model) or an exit code."""
    from .html import render_page

    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, args.strict):
        return 1
    try:
        if args.diff_base:
            # Diff first so `diff:` selectors work; then select.
            from . import diff

            model, pos = project.build(schema, by_group=args.by_group)
            old = diff.schema_at_ref(args.diff_base, project.inputs)
            diff.annotate_model(model, diff.diff_schemas(old, schema), args.diff_base)
            expr = selector_expr(args.select, args.exclude)
            if expr:
                from .project import select_model

                model = select_model(model, expr)
                pos = {k: v for k, v in pos.items() if any(t["id"] == k for t in model["tables"])}
        else:
            model, pos = project.build(schema, select=selector_expr(args.select, args.exclude), by_group=args.by_group)
    except SelectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        from .diff import DiffError

        if isinstance(e, DiffError):
            print(f"error: {e}", file=sys.stderr)
            return 2
        raise
    return render_page(model, pos, _title(project)), model


def cmd_build(args) -> int:
    res = _built_page(args)
    if isinstance(res, int):
        return res
    page, model = res
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out} ({len(model['tables'])} tables, {len(model['rels'])} relationships)")
    return 0


def cmd_share(args) -> int:
    from . import share

    res = _built_page(args)
    if isinstance(res, int):
        return res
    page, model = res
    key = share.share_key(args.paths, selector_expr(args.select, args.exclude))
    try:
        r = share.publish(page, _title(_open(args)), key, public=args.public, new=args.new)
    except share.ShareError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    verb = "Updated" if r.updated else "Shared"
    print(f"{verb} {len(model['tables'])} tables ({'public' if r.public else 'secret'} gist {r.gist_url})")
    print(f"Link: {r.link}")
    print(f"  (if that doesn't load: {r.alt_link})")
    return 0


def cmd_export(args) -> int:
    from . import export

    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, args.strict):
        return 1
    try:
        model, pos = project.build(schema, select=selector_expr(args.select, args.exclude), by_group=args.by_group)
    except SelectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    regions = args.regions or args.by_group
    only = None
    if not args.focus and (args.select or args.exclude) and not args.by_group:
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
    if fmt not in ("svg", "png", "drawio"):
        print("error: output must end in .svg, .png or .drawio", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "drawio":
        out.write_text(
            export.render_drawio(model, pos, only=only, mode=args.mode, title=_title(project), regions=regions),
            encoding="utf-8",
        )
        print(f"Wrote {out} ({len(only) if only else len(model['tables'])} tables)")
        return 0
    svg = export.render_svg(model, pos, only=only, mode=args.mode, embed_font=(fmt == "svg"), regions=regions)
    if fmt == "svg":
        out.write_text(svg, encoding="utf-8")
    else:
        scale = export.png_scale(svg, args.scale)
        if scale < args.scale:
            note = f"--scale lowered to {scale:.2f} to keep the PNG within {export.MAX_PNG_SIDE} px"
            print(f"note: {note}", file=sys.stderr)
        out.write_bytes(export.svg_to_png(svg, scale))
    print(f"Wrote {out} ({len(only) if only else len(model['tables'])} tables)")
    return 0


def cmd_layout(args) -> int:
    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, False):
        return 1
    model, pos = project.build(schema, reset=args.reset, by_group=args.by_group)
    project.save_positions(model, pos)
    print(f"Wrote {project.sidecar} ({len(pos)} tables)")
    return 0


def cmd_import_dbt(args) -> int:
    from .dbt import DbtImportError, import_dbt, stale_files, write_result
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
            infer_fks=args.infer_fks,
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
    for s in result.skipped:
        print(f"skipped: {s}", file=sys.stderr)
    for s in result.inferred:
        print(f"inferred: {s}", file=sys.stderr)
    inferred = f" ({len(result.inferred)} inferred)" if args.infer_fks else ""
    if args.check:
        stale = stale_files(result, out)
        if stale:
            for s in stale:
                print(f"stale: {s}", file=sys.stderr)
            print(
                f"error: schema files are out of date; run `qdbd import dbt {args.manifest} -o {args.output}` "
                "and commit the result",
                file=sys.stderr,
            )
            return 1
        print(f"Up to date: {out}: {result.tables} tables, {result.relationships} relationships{inferred}")
        return 0
    written = write_result(result, out)
    where = str(out) if not split else f"{out}/ ({len(written)} files)"
    print(f"Wrote {where}: {result.tables} tables, {result.relationships} relationships{inferred}")
    if result.no_columns and not result.catalog:
        print(
            f"hint: {result.no_columns} of {result.tables} tables have no known columns (undocumented in dbt). "
            "Run `dbt docs generate` so target/catalog.json lists every column and type; "
            "--infer-fks can only link columns it can see.",
            file=sys.stderr,
        )
    if result.tables and not result.relationships:
        print(
            "hint: no relationships found; add `relationships` tests or foreign_key constraints in dbt"
            + ("" if args.infer_fks else ", or try --infer-fks"),
            file=sys.stderr,
        )
    return 0


def cmd_convert(args) -> int:
    from . import convert, layout
    from .parser import compile_sources

    inputs = [Path(p) for p in args.paths]
    try:
        project = Project.open(inputs)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = Path(args.output) if args.output else None
    to_dir = out is not None and (len(project.files) > 1 or inputs[0].is_dir() or out.suffix == "" or out.is_dir())
    if out is None and len(project.files) > 1:
        print("error: several files: give -o DIR", file=sys.stderr)
        return 2
    sources = []
    for f in project.files:
        root = next((p for p in inputs if p.is_dir() and f.resolve().is_relative_to(p.resolve())), None)
        rel = f.resolve().relative_to(root.resolve()).as_posix() if root else f.name
        sources.append((str(f), rel, f.read_text(encoding="utf-8")))
    schema = compile_sources([(d, t) for d, _, t in sources])
    if not _print_diagnostics(schema, False):
        return 1
    res = convert.convert(sources, args.to, split_groups=to_dir)
    for w in res.warnings:
        print(w.format(), file=sys.stderr)
    again = compile_sources(list(res.files.items()))
    if again.errors or convert.canonical(again, res.lost) != convert.canonical(schema, res.lost):
        for d in again.errors:
            print(d.format(), file=sys.stderr)
        print("error: converted schema differs from the input (please report this as a bug)", file=sys.stderr)
        return 1
    if out is None:
        sys.stdout.write(next(iter(res.files.values())))
        if res.layout:
            print("warning: [layout] positions not written (give -o to write a layout file)", file=sys.stderr)
        return 0
    written = []
    if to_dir:
        for name, text in res.files.items():
            p = out / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            written.append(p)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(next(iter(res.files.values())), encoding="utf-8")
        written.append(out)
    if res.layout:
        sidecar = layout.default_sidecar(written, [out])
        positions = {**{k: tuple(v) for k, v in res.layout.items()}, **layout.read_sidecar(sidecar)}
        layout.write_sidecar(sidecar, positions)
        written.append(sidecar)
    print(f"Wrote {', '.join(str(p) for p in written)}")
    return 0


def cmd_path(args) -> int:
    from . import export
    from .jsrt import runtime

    project = _open(args)
    schema = project.compile()
    if not _print_diagnostics(schema, False):
        return 1
    from .measure import model_json

    model = model_json(schema)
    ends = []
    for name in (args.source, args.target):
        t = export.find_table(model, name)
        if t is None:
            print(f"error: table '{name}' not found", file=sys.stderr)
            return 1
        ends.append(t)
    rt = runtime()
    rt.load("render.js")
    steps = rt.call("qdbdFindPath", model, ends[0]["id"], ends[1]["id"])
    a, b = ends[0]["name"], ends[1]["name"]
    if steps is None:
        print(f"No relationship path between {a} and {b}.")
        return 1
    by_id = {t["id"]: t for t in model["tables"]}
    card = {"one": "1", "many": "N", "zeroOne": "0..1", "zeroMany": "0..N"}

    def end(e, cols):
        t = by_id[e["t"]]
        names = [c["name"] for k in cols for c in t["cols"] if c["id"] == k]
        if not names:
            return t["name"]
        return f"{t['name']}.{names[0]}" if len(names) == 1 else f"{t['name']}.({', '.join(names)})"

    print(f"{a} -> {b}: {len(steps)} join(s)")
    for st in steps:
        pairs = st["pairs"]
        joined = f"{end(st['from'], [p[0] for p in pairs])} -> {end(st['to'], [p[1] for p in pairs])}"
        print(f"  {joined} ({card[st['from']['card']]}:{card[st['to']['card']]})")
    if steps:
        print()
        print(rt.call("qdbdPathSql", model, ends[0]["id"], steps))
    return 0


def cmd_diff(args) -> int:
    from . import diff

    paths = [Path(p) for p in args.paths]
    try:
        if args.base:
            new = Project.open(paths).compile()
            old = diff.schema_at_ref(args.base, paths)
            old_label, new_label = args.base, "working tree"
        else:
            if len(paths) != 2:
                print("error: give two paths (OLD NEW), or --base REF with the schema path(s)", file=sys.stderr)
                return 2
            old = Project.open([paths[0]]).compile()
            new = Project.open([paths[1]]).compile()
            old_label, new_label = str(paths[0]), str(paths[1])
    except diff.DiffError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for label, schema in ((old_label, old), (new_label, new)):
        if schema.errors:
            print(f"warning: {label} has {len(schema.errors)} error(s); comparing what parsed", file=sys.stderr)
    d = diff.diff_schemas(old, new)
    if args.format == "markdown":
        text = diff.format_markdown(d, old_label, new_label)
    elif args.format == "json":
        text = diff.format_json(d)
    else:
        text = diff.format_text(d, old_label, new_label)
    if args.output:
        Path(args.output).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    else:
        print(text)
    return 1 if (args.exit_code and not d.empty) else 0


def cmd_serve(args) -> int:
    from .serve import serve

    project = _open(args)
    # Without --port, a busy 8765 (e.g. a second `qdbd serve`) moves on to the next free port.
    port, tries = (args.port, 1) if args.port is not None else (8765, 20)
    if args.read_only and args.embed:
        print("error: --read-only and --embed don't go together", file=sys.stderr)
        return 2
    return serve(
        project,
        port=port,
        open_browser=not args.no_open,
        read_only=args.read_only,
        tries=tries,
        embed=args.embed,
        diff_base=args.diff_base,
    )


def _mcp_target(paths: list[Path]):
    """The one project PATHs name: a dbt manifest (or its target/ folder), else schema files. None if they mix."""
    from .targets import Target, target_title

    def dbt_manifest(p: Path) -> Path | None:
        if p.is_file() and p.suffix.lower() == ".json":
            return p
        if p.is_dir() and (p / "manifest.json").is_file() and not any(p.glob("*.txt")) and not any(p.glob("*.dbml")):
            return p / "manifest.json"
        return None

    manifests = [dbt_manifest(p) for p in paths]
    if any(manifests):
        if len(paths) != 1:
            return None
        m = manifests[0].resolve()
        root = m.parent.parent if m.parent.name == "target" else m.parent
        return Target(f"{root.name} (dbt)", "dbt", root, (os.path.relpath(m, root),))
    if len(paths) == 1:
        p = paths[0].resolve()
        root, rel = (p, (".",)) if p.is_dir() else (p.parent, (p.name,))
    else:
        root = Path(os.path.commonpath([p.resolve() for p in paths]))
        rel = tuple(os.path.relpath(p.resolve(), root) for p in paths)
    return Target(target_title(root, rel) if len(rel) == 1 else root.name or "schema", "schema", root, rel)


def cmd_mcp(args) -> int:
    from .agent import Workspace

    paths = [Path(p).resolve() for p in args.paths]
    for p in paths:
        if not p.exists():
            print(f"error: no such file or directory: {p}", file=sys.stderr)
            return 2
    root = Path(args.root or os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()
    if not root.is_dir():
        print(f"error: --root {root} is not a folder", file=sys.stderr)
        return 2
    fixed = _mcp_target(paths) if paths else None
    if paths and fixed is None:
        print("error: give either schema files/folders or one dbt manifest, not both", file=sys.stderr)
        return 2
    refused = None
    system = Path(os.environ.get("SystemRoot", "/nonexistent")).resolve()
    if not paths and (root == Path(root.anchor) or root == Path.home().resolve() or root == system):
        refused = (
            f"qdbd mcp was started in {root}, which is too broad to search; "
            "start it with --root PROJECT_FOLDER or a schema path"
        )
    os.chdir(root)

    from . import mcp
    from .jsrt import runtime

    rfile, wfile = mcp.isolate_stdio()
    runtime()  # V8 starts on this thread, outside any event loop
    ws = Workspace(root, fixed, infer_fks=args.infer_fks, refused=refused)
    what = fixed.name if fixed else f"schema projects under {root}"
    mcp._Log().line(f"qdbd {__version__} serving {what} over stdio")
    return mcp.serve(mcp.Server(ws), rfile, wfile)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qdbd", description="Compile QuickDBD schema files into interactive ER diagrams.")
    p.add_argument("--version", action="version", version=f"qdbd {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def paths(sp):
        sp.add_argument("paths", nargs="+", metavar="PATH", help="schema .txt/.dbml file(s) or folder(s) (recursive)")

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
    sp.add_argument(
        "--format",
        choices=["text", "github", "json"],
        default="text",
        help="github: also emit GitHub Actions annotations (inline on PR lines); json: a machine-readable report",
    )
    sp.add_argument(
        "--symbols", action="store_true", help="with --format json: also list tables, columns and relationships"
    )
    sp.add_argument(
        "--stdin-file",
        metavar="PATH",
        help="read this schema file's text from stdin instead of disk (an editor's unsaved buffer)",
    )
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("build", help="write an interactive HTML diagram")
    paths(sp)
    sp.add_argument("-o", "--output", default="diagram.html")
    selectors(sp)
    sp.add_argument(
        "--diff-base", metavar="GIT_REF", help="colour tables/columns changed since this git ref (e.g. origin/main)"
    )
    sp.add_argument("--by-group", action="store_true", help=BY_GROUP_HELP)
    sp.add_argument("--layout", help="layout sidecar file (default: next to the schema)")
    sp.add_argument("--strict", action="store_true")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("share", help="publish the diagram as a GitHub gist and print a link (needs the gh CLI)")
    paths(sp)
    selectors(sp)
    sp.add_argument(
        "--diff-base", metavar="GIT_REF", help="colour tables/columns changed since this git ref (e.g. origin/main)"
    )
    sp.add_argument("--by-group", action="store_true", help=BY_GROUP_HELP)
    sp.add_argument("--layout", help="layout sidecar file (default: next to the schema)")
    sp.add_argument("--strict", action="store_true")
    sp.add_argument("--public", action="store_true", help="list the gist publicly (default: secret, link-only)")
    sp.add_argument("--new", action="store_true", help="make a new gist instead of updating the last one")
    sp.set_defaults(func=cmd_share)

    sp = sub.add_parser("export", help="write a PNG, SVG or draw.io file")
    paths(sp)
    sp.add_argument("-o", "--output", required=True, help="out.png, out.svg or out.drawio")
    selectors(sp)
    sp.add_argument("--focus", metavar="TABLE", help="only this table and its neighbours")
    sp.add_argument("--depth", type=int, default=1, help="relationship hops around --focus (default 1)")
    sp.add_argument("--mode", choices=["full", "keys", "header"], default="full", help="collapse mode")
    sp.add_argument("--scale", type=float, default=2.0, help="PNG pixel scale (default 2)")
    sp.add_argument("--regions", action="store_true", help="draw a shaded area per file / dbt folder")
    sp.add_argument("--by-group", action="store_true", help=BY_GROUP_HELP)
    sp.add_argument("--layout")
    sp.add_argument("--strict", action="store_true")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("layout", help="write table positions to the layout sidecar")
    paths(sp)
    sp.add_argument("--reset", action="store_true", help="discard saved positions and auto-layout everything")
    sp.add_argument("--by-group", action="store_true", help=BY_GROUP_HELP)
    sp.add_argument("--layout")
    sp.set_defaults(func=cmd_layout)

    sp = sub.add_parser("path", help="shortest join path between two tables, with a SQL JOIN snippet")
    paths(sp)
    sp.add_argument("--from", dest="source", required=True, metavar="TABLE")
    sp.add_argument("--to", dest="target", required=True, metavar="TABLE")
    sp.set_defaults(func=cmd_path)

    sp = sub.add_parser("diff", help="compare schema versions (two paths, or --base GIT_REF vs working tree)")
    sp.add_argument("paths", nargs="+", metavar="PATH", help="OLD NEW, or the schema path(s) with --base")
    sp.add_argument("--base", metavar="GIT_REF", help="compare PATH(s) at this git ref with the working tree")
    sp.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    sp.add_argument("-o", "--output", help="write to a file instead of stdout")
    sp.add_argument("--exit-code", action="store_true", help="exit 1 when there are changes (like git diff)")
    sp.set_defaults(func=cmd_diff)

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
    dp.add_argument(
        "--infer-fks",
        action="store_true",
        help="also link <entity>_id columns to the table named after the entity when no relationship is declared",
    )
    dp.add_argument(
        "--check", action="store_true", help="don't write; exit 1 if the files at -o are out of date (for CI)"
    )
    dp.set_defaults(func=cmd_import_dbt)

    sp = sub.add_parser("convert", help="convert schema files between QuickDBD text and DBML")
    sp.add_argument("paths", nargs="+", metavar="PATH", help="schema .txt/.dbml file(s) or folder(s) (recursive)")
    sp.add_argument("--to", required=True, choices=["dbml", "quickdbd"], help="target syntax")
    sp.add_argument(
        "-o", "--output", help="output file, or a directory (keeps relative paths; DBML TableGroups become files)"
    )
    sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("serve", help="live editor: reload on save, drag tables to arrange")
    paths(sp)
    sp.add_argument("--port", type=int, help="port to listen on (default: 8765, or the next free one)")
    sp.add_argument("--layout")
    sp.add_argument("--no-open", action="store_true", help="don't open a browser")
    sp.add_argument(
        "--read-only",
        action="store_true",
        help="live view only: no editor, nothing saved; safe to share through a tunnel",
    )
    sp.add_argument(
        "--embed",
        action="store_true",
        help="for the VS Code extension's preview: no editor pane, dragging saves the layout",
    )
    sp.add_argument(
        "--diff-base", metavar="GIT_REF", help="colour tables/columns changed since this git ref (e.g. origin/main)"
    )
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser(
        "mcp",
        help="MCP server over stdio: lets AI agents (Claude, Copilot, Cursor) query the schema",
        description="Serve the schema to AI agents over the Model Context Protocol (stdio). With no PATH, every "
        "schema project found under the root is served.",
    )
    sp.add_argument(
        "paths", nargs="*", metavar="PATH", help="serve just this schema (files, a folder, or a dbt manifest.json)"
    )
    sp.add_argument("--root", metavar="DIR", help="project folder (default: $CLAUDE_PROJECT_DIR, else the cwd)")
    sp.add_argument(
        "--infer-fks", action="store_true", help="dbt manifests: also link <entity>_id columns (labelled inferred)"
    )
    sp.set_defaults(func=cmd_mcp)
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
