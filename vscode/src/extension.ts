/* QuickDBD for VS Code: highlighting, live diagnostics, outline and go-to-definition, and the qdbd diagram
 * as a side preview. Everything schema-aware comes from the `qdbd` CLI; see checker.ts and preview.ts. */
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { Checker, LANGUAGE } from "./checker.ts";
import { Qdbd } from "./cli.ts";
import { exportDiagram, share, type Format } from "./export.ts";
import { Previews } from "./preview.ts";
import { looksLikeQuickdbd } from "./schema.ts";
import { registerSymbols } from "./symbols.ts";

const TYPING_DELAY = 300;

export function activate(context: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("QuickDBD");
  const qdbd = new Qdbd(log);
  const checker = new Checker(qdbd, log);
  const previews = new Previews(qdbd, checker, log);

  const withDoc = (fn: (doc: vscode.TextDocument) => unknown) => () => {
    const doc = vscode.window.activeTextEditor?.document;
    if (doc?.languageId === LANGUAGE) return fn(doc);
    void vscode.window.showInformationMessage("Open a QuickDBD schema file first.");
  };
  const exporter = (format: Format) => withDoc((doc) => exportDiagram(qdbd, checker, doc, format));

  context.subscriptions.push(
    log,
    checker,
    previews,
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
    vscode.commands.registerCommand("quickdbd.share", withDoc((doc) => share(qdbd, checker, doc))),
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
