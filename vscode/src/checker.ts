/* Runs `qdbd check --format json --symbols` for a schema (with the active file's unsaved text on stdin),
 * publishes the diagnostics, and keeps the report for the outline, go-to-definition and the preview. */
import * as path from "node:path";
import * as vscode from "vscode";
import type { Qdbd } from "./cli.ts";
import { findTarget } from "./target.ts";
import { targetKey, type Report, type Target } from "./schema.ts";

export const LANGUAGE = "quickdbd";

interface Entry {
  target: Target;
  report?: Report;
  files: Set<string>; // uris this target last published diagnostics for
  timer?: ReturnType<typeof setTimeout>;
  seq: number;
  pending?: Promise<void>; // settles when the scheduled check(s) are done
  settle?: () => void;
}

const READY_TIMEOUT = 10000;
const TARGET_TTL = 5000; // findTarget may read every .txt in a folder; don't redo it on each keystroke

export class Checker implements vscode.Disposable {
  readonly diagnostics = vscode.languages.createDiagnosticCollection("qdbd");
  private readonly entries = new Map<string, Entry>();
  private readonly targets = new Map<string, { target: Target; at: number }>();
  private readonly changed = new vscode.EventEmitter<Target>();
  readonly onDidUpdate = this.changed.event;

  private readonly qdbd: Qdbd;
  private readonly log: vscode.OutputChannel;

  constructor(qdbd: Qdbd, log: vscode.OutputChannel) {
    this.qdbd = qdbd;
    this.log = log;
  }

  targetFor(doc: vscode.TextDocument): Target {
    const file = doc.uri.fsPath;
    const hit = this.targets.get(file);
    if (hit && Date.now() - hit.at < TARGET_TTL) return hit.target;
    const target = findTarget(file, vscode.workspace.getWorkspaceFolder(doc.uri)?.uri.fsPath);
    this.targets.set(file, { target, at: Date.now() });
    return target;
  }

  /** The latest report for the schema `doc` belongs to, and the doc's path as the report spells it. */
  reportFor(doc: vscode.TextDocument): { target: Target; report: Report; file: string } | undefined {
    const target = this.targetFor(doc);
    const report = this.entries.get(targetKey(target))?.report;
    return report && { target, report, file: relative(target, doc.uri.fsPath) };
  }

  /** Wait for the check of `doc`'s schema that's due or running, so answers match the text as it is now.
   * VS Code caches outline results per document version, so answering early would stick. */
  async ready(doc: vscode.TextDocument): Promise<void> {
    let e = this.entries.get(targetKey(this.targetFor(doc)));
    if (!e?.report && !e?.pending) {
      this.schedule(doc, 0);
      e = this.entries.get(targetKey(this.targetFor(doc)));
    }
    if (e?.pending) await Promise.race([e.pending, new Promise((r) => setTimeout(r, READY_TIMEOUT))]);
  }

  /** The latest report for a schema, opened in an editor or not. */
  reportOf(target: Target): Report | undefined {
    return this.entries.get(targetKey(target))?.report;
  }

  /** Check a schema from disk (the sidebar's, with no editor open). Skipped while a check of it is due, or while an
   * editor has unsaved text in it: the editor's checks use that text, and a check from disk would undo them. */
  async checkTarget(target: Target): Promise<void> {
    const key = targetKey(target);
    let e = this.entries.get(key);
    if (!e) this.entries.set(key, (e = { target, files: new Set(), seq: 0 }));
    if (e.pending) return e.pending;
    const dirty = vscode.workspace.textDocuments.some(
      (d) => d.isDirty && d.languageId === LANGUAGE && d.uri.scheme === "file" && targetKey(this.targetFor(d)) === key,
    );
    if (!dirty) await this.run(e, undefined, ++e.seq);
  }

  reports(): { target: Target; report: Report }[] {
    return [...this.entries.values()].flatMap((e) => (e.report ? [{ target: e.target, report: e.report }] : []));
  }

  /** Check `doc`'s schema after `delay` ms; later calls for the same schema replace earlier ones. */
  schedule(doc: vscode.TextDocument, delay: number): void {
    if (doc.languageId !== LANGUAGE || doc.uri.scheme !== "file") return;
    const target = this.targetFor(doc);
    const key = targetKey(target);
    let e = this.entries.get(key);
    if (!e) this.entries.set(key, (e = { target, files: new Set(), seq: 0 }));
    const entry = e;
    entry.pending ??= new Promise((resolve) => (entry.settle = resolve));
    clearTimeout(entry.timer);
    entry.timer = setTimeout(() => {
      entry.timer = undefined;
      const seq = ++entry.seq;
      void this.run(entry, doc, seq).finally(() => {
        if (seq !== entry.seq || entry.timer) return; // a newer check settles it
        entry.pending = undefined;
        entry.settle?.();
      });
    }, delay);
  }

  private async run(e: Entry, doc: vscode.TextDocument | undefined, seq: number): Promise<void> {
    const strict = vscode.workspace.getConfiguration("quickdbd").get<boolean>("strict") ? ["--strict"] : [];
    const unsaved = doc?.isDirty && !doc.isClosed ? ["--stdin-file", relative(e.target, doc.uri.fsPath)] : [];
    const args = ["check", "--format", "json", "--symbols", ...strict, ...unsaved, ...e.target.paths];
    const res = await this.qdbd.run(args, e.target.cwd, unsaved.length ? doc?.getText() : undefined);
    if (!res || seq !== e.seq) return; // no qdbd, or a newer check started
    let report: Report;
    try {
      report = JSON.parse(res.stdout) as Report;
    } catch {
      this.log.appendLine(`qdbd ${args.join(" ")} (in ${e.target.cwd}) failed:\n${res.stderr || res.stdout}`);
      return;
    }
    e.report = report;
    this.publish(e, report);
    this.changed.fire(e.target);
  }

  private publish(e: Entry, report: Report): void {
    const byFile = new Map<string, vscode.Diagnostic[]>();
    for (const d of report.diagnostics) {
      const uri = vscode.Uri.file(path.resolve(e.target.cwd, d.path)).toString();
      const line = Math.max(0, d.line - 1);
      const diag = new vscode.Diagnostic(
        new vscode.Range(line, 0, line, Number.MAX_SAFE_INTEGER),
        d.message,
        d.severity === "warning" ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Error,
      );
      diag.source = "qdbd";
      byFile.set(uri, [...(byFile.get(uri) ?? []), diag]);
    }
    for (const uri of e.files) if (!byFile.has(uri)) this.diagnostics.delete(vscode.Uri.parse(uri));
    for (const [uri, diags] of byFile) this.diagnostics.set(vscode.Uri.parse(uri), diags);
    e.files = new Set(byFile.keys());
  }

  dispose(): void {
    for (const e of this.entries.values()) clearTimeout(e.timer);
    this.diagnostics.dispose();
    this.changed.dispose();
  }
}

/** A file's path as qdbd reports it: relative to the directory qdbd ran in. */
export function relative(target: Target, file: string): string {
  return path.relative(target.cwd, file);
}
