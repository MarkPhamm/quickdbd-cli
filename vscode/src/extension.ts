/* QuickDBD for VS Code: highlighting, live diagnostics, outline and go-to-definition, the qdbd diagram as a side
 * preview, and the CLI's other commands (export, share, compare, dbt import), all without a terminal. Everything
 * schema-aware comes from the `qdbd` CLI, which the extension can install for itself (cli.ts). */
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { Checker, LANGUAGE } from "./checker.ts";
import { Qdbd } from "./cli.ts";
import { pickRef } from "./compare.ts";
import { importDbt, type ImportOptions } from "./dbt.ts";
import { exportDiagram, share, type Format } from "./export.ts";
import { Previews } from "./preview.ts";
import { looksLikeQuickdbd } from "./schema.ts";
import { registerSymbols } from "./symbols.ts";

const TYPING_DELAY = 300;

export function activate(context: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("QuickDBD");
  const qdbd = new Qdbd(log, context.globalStorageUri.fsPath);
  const checker = new Checker(qdbd, log);
  const previews = new Previews(qdbd, checker, log);

  // `opts` comes from a keybinding's or a test's arguments; menus pass other things (a Uri), so it's checked.
  const withDoc = (fn: (doc: vscode.TextDocument, opts: Record<string, unknown>) => unknown) => (opts?: unknown) => {
    const doc = vscode.window.activeTextEditor?.document;
    if (doc?.languageId === LANGUAGE) return fn(doc, opts && typeof opts === "object" ? { ...opts } : {});
    void vscode.window.showInformationMessage("Open a QuickDBD schema file first.");
  };
  const str = (v: unknown) => (typeof v === "string" && v ? v : undefined);
  const exporter = (format: Format) =>
    withDoc((doc, opts) => exportDiagram(qdbd, checker, doc, format, str(opts.output)));

  context.subscriptions.push(
    log,
    qdbd,
    checker,
    previews,
    qdbd.onDidInstall(() => vscode.workspace.textDocuments.forEach((d) => checker.schedule(d, 0))),
    registerSymbols(checker),
    vscode.workspace.onDidOpenTextDocument((doc) => void opened(doc, checker)),
    vscode.workspace.onDidChangeTextDocument((e) => checker.schedule(e.document, TYPING_DELAY)),
    vscode.workspace.onDidSaveTextDocument((doc) => checker.schedule(doc, 0)),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("quickdbd.qdbdPath")) qdbd.reset();
      if (e.affectsConfiguration("quickdbd")) vscode.workspace.textDocuments.forEach((d) => checker.schedule(d, 0));
    }),
    vscode.commands.registerCommand("quickdbd.openPreview", withDoc((doc) => previews.show(doc))),
    vscode.commands.registerCommand("quickdbd.exportPng", exporter("png")),
    vscode.commands.registerCommand("quickdbd.exportSvg", exporter("svg")),
    vscode.commands.registerCommand("quickdbd.exportDrawio", exporter("drawio")),
    vscode.commands.registerCommand("quickdbd.exportHtml", exporter("html")),
    vscode.commands.registerCommand("quickdbd.share", withDoc((doc) => share(qdbd, checker, doc))),
    vscode.commands.registerCommand(
      "quickdbd.compare",
      withDoc(async (doc, opts) => {
        const ref = str(opts.ref) ?? (await pickRef(checker.targetFor(doc).cwd));
        if (ref) await previews.show(doc, ref);
      }),
    ),
    vscode.commands.registerCommand("quickdbd.importDbt", (opts?: ImportOptions) =>
      importDbt(qdbd, (doc) => previews.show(doc), {
        manifest: str(opts?.manifest),
        output: str(opts?.output),
      }),
    ),
    vscode.commands.registerCommand("quickdbd.installCli", () => qdbd.install()),
  );
  vscode.workspace.textDocuments.forEach((doc) => void opened(doc, checker));
}

/** Switch a plain .txt that is a QuickDBD schema to the QuickDBD language, then check it. */
async function opened(doc: vscode.TextDocument, checker: Checker): Promise<void> {
  if (doc.languageId === "plaintext" && doc.uri.scheme === "file" && /\.txt$/i.test(doc.uri.fsPath)) {
    if (!vscode.workspace.getConfiguration("quickdbd").get<boolean>("autoDetect", true)) return;
    if (!hasSidecar(doc.uri.fsPath) && !looksLikeQuickdbd(doc.getText())) return;
    await vscode.languages.setTextDocumentLanguage(doc, LANGUAGE); // reopens it as QuickDBD, which lands here again
    return;
  }
  checker.schedule(doc, 0);
}

function hasSidecar(file: string): boolean {
  const dir = path.dirname(file);
  const own = path.join(dir, path.basename(file).replace(/\.txt$/i, "") + ".layout.json");
  return fs.existsSync(own) || fs.existsSync(path.join(dir, "qdbd.layout.json"));
}

export function deactivate(): void {}
