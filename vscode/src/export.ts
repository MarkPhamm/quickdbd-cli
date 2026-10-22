/* Export PNG / SVG / draw.io and share as a gist: thin wrappers over `qdbd export` and `qdbd share`. */
import * as path from "node:path";
import * as vscode from "vscode";
import type { Checker } from "./checker.ts";
import type { Qdbd } from "./cli.ts";
import { firstUrl, tableAt } from "./schema.ts";

const FORMATS = { png: "PNG image", svg: "SVG image", drawio: "draw.io diagram" } as const;
export type Format = keyof typeof FORMATS;

export async function exportDiagram(qdbd: Qdbd, checker: Checker, doc: vscode.TextDocument, format: Format) {
  const target = checker.targetFor(doc);
  const r = checker.reportFor(doc);
  const ed = vscode.window.activeTextEditor;
  const here = r && ed?.document === doc ? tableAt(r.report, r.file, ed.selection.active.line + 1) : undefined;
  let focus: string | undefined;
  if (here) {
    const whole = "Whole diagram";
    const pick = await vscode.window.showQuickPick([whole, `${here.name} and its neighbours`], { title: "Export" });
    if (!pick) return;
    focus = pick === whole ? undefined : here.name;
  }
  const stem = focus ?? (target.paths[0] === "." ? path.basename(target.cwd) : path.parse(target.paths[0]).name);
  const out = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(target.cwd, `${stem}.${format}`)),
    filters: { [FORMATS[format]]: [format] },
  });
  if (!out) return;
  const args = ["export", ...target.paths, "-o", out.fsPath, ...(focus ? ["--focus", focus] : [])];
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Exporting ${path.basename(out.fsPath)}…` },
    () => qdbd.run(args, target.cwd),
  );
  if (!res) return;
  if (res.code !== 0) {
    void vscode.window.showErrorMessage(`qdbd export failed: ${(res.stderr || res.stdout).trim()}`);
    return;
  }
  const open = await vscode.window.showInformationMessage(`Wrote ${path.basename(out.fsPath)}`, "Open");
  if (open) void vscode.commands.executeCommand("vscode.open", out);
}

export async function share(qdbd: Qdbd, checker: Checker, doc: vscode.TextDocument) {
  const target = checker.targetFor(doc);
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Publishing the diagram as a secret gist…" },
    () => qdbd.run(["share", ...target.paths], target.cwd),
  );
  if (!res) return;
  // "Link: <viewer url>" is the one to share; the first URL printed is the gist itself.
  const url = res.code === 0 ? (/^Link:\s*(\S+)/m.exec(res.stdout)?.[1] ?? firstUrl(res.stdout)) : undefined;
  if (!url) {
    void vscode.window.showErrorMessage(`qdbd share failed: ${(res.stderr || res.stdout).trim()}`);
    return;
  }
  await vscode.env.clipboard.writeText(url);
  const open = await vscode.window.showInformationMessage(`Link copied: ${url}`, "Open");
  if (open) void vscode.env.openExternal(vscode.Uri.parse(url));
}
