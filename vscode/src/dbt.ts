/* Import dbt Project: `qdbd import dbt` on a target/manifest.json, then the schema it wrote opens with its diagram. */
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { LANGUAGE } from "./checker.ts";
import type { Qdbd } from "./cli.ts";

/** Paths that skip the questions, for keybindings and tests; `output` is relative to the dbt project. */
export interface ImportOptions {
  manifest?: string;
  output?: string;
}

export async function importDbt(
  qdbd: Qdbd,
  preview: (doc: vscode.TextDocument) => Promise<void>,
  opts: ImportOptions = {},
): Promise<void> {
  const manifest = opts.manifest ?? (await pickManifest());
  if (!manifest) return;
  const project = path.dirname(path.dirname(path.resolve(manifest))); // the dbt project, above target/
  const output = opts.output ? path.resolve(project, opts.output) : await pickOutput(project);
  if (!output) return;
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Importing the dbt project…" },
    () => qdbd.run(["import", "dbt", manifest, "-o", output], project),
  );
  if (!res) return;
  if (res.code !== 0) {
    void vscode.window.showErrorMessage(`qdbd import failed: ${(res.stderr || res.stdout).trim()}`);
    return;
  }
  const first = output.toLowerCase().endsWith(".txt") ? output : firstSchema(output);
  if (!first) return;
  let doc = await vscode.workspace.openTextDocument(first);
  if (doc.languageId !== LANGUAGE) doc = await vscode.languages.setTextDocumentLanguage(doc, LANGUAGE);
  await vscode.window.showTextDocument(doc);
  await preview(doc);
}

async function pickManifest(): Promise<string | undefined> {
  const found = await vscode.workspace.findFiles("**/target/manifest.json", "**/{node_modules,dbt_packages,.venv}/**", 20);
  if (found.length === 1) return found[0].fsPath;
  const browse = "Browse…";
  if (found.length > 1) {
    const items = [...found.map((uri) => ({ label: vscode.workspace.asRelativePath(uri), uri })), { label: browse }];
    const pick = await vscode.window.showQuickPick(items, { title: "Import dbt Project", placeHolder: "Which manifest.json?" });
    if (!pick) return undefined;
    if ("uri" in pick) return pick.uri.fsPath;
  }
  const picked = await vscode.window.showOpenDialog({
    title: "The dbt project's target/manifest.json (from dbt compile; dbt docs generate adds column types)",
    filters: { "dbt manifest": ["json"] },
  });
  return picked?.[0]?.fsPath;
}

async function pickOutput(project: string): Promise<string | undefined> {
  const split = "One file per dbt folder";
  const pick = await vscode.window.showQuickPick(
    [
      { label: split, description: "erd/staging.txt, erd/marts.txt, … in the dbt project" },
      { label: "One file…", description: "choose where to save it" },
    ],
    { title: "Import dbt Project" },
  );
  if (!pick) return undefined;
  if (pick.label === split) return path.join(project, "erd");
  const out = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(project, "schema.txt")),
    filters: { "QuickDBD schema": ["txt"] },
  });
  return out?.fsPath;
}

function firstSchema(dir: string): string | undefined {
  const name = fs
    .readdirSync(dir)
    .filter((f) => f.toLowerCase().endsWith(".txt"))
    .sort()[0];
  return name && path.join(dir, name);
}
