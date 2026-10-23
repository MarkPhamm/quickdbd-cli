/* QuickDBD for VS Code (QuickDBD and DBML schemas): highlighting, live diagnostics, outline and go-to-definition, the qdbd diagram as a side
 * preview, the CLI's other commands (export, share, compare, dbt import), and a sidebar listing every schema, all
 * without a terminal. Everything schema-aware comes from the `qdbd` CLI, which the extension can install for itself
 * (cli.ts). */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import { Checker, LANGUAGE } from "./checker.ts";
import { Qdbd } from "./cli.ts";
import { pickRef } from "./compare.ts";
import { convertSchema } from "./convert.ts";
import { importDbt, type ImportOptions } from "./dbt.ts";
import { exportDiagram, share, type Format } from "./export.ts";
import { Previews } from "./preview.ts";
import type { Target } from "./schema.ts";
import { isSchemaArg, Sidebar, type Node } from "./sidebar.ts";
import { registerSymbols } from "./symbols.ts";
import { schemaLanguage, targetTitle } from "./target.ts";

const TYPING_DELAY = 300;

const STARTER = `# Customers: one row per person who has bought something.
Customer
-
CustomerId PK int
Name string
Email string UNIQUE

# Orders: each one belongs to a customer.
Order
-
OrderId PK int
CustomerId int FK >- Customer.CustomerId
OrderedAt datetime
Total money
`;

/** For tests: the sidebar's schemas, with their table counts once checked. */
export interface Api {
  schemas(): Promise<{ title: string; tables?: number; target: Target; file: string }[]>;
}

export function activate(context: vscode.ExtensionContext): Api {
  const log = vscode.window.createOutputChannel("QuickDBD");
  const qdbd = new Qdbd(log, context.globalStorageUri.fsPath);
  const checker = new Checker(qdbd, log);
  const previews = new Previews(qdbd, checker, log);
  const sidebar = new Sidebar(checker, qdbd);

  /** The schema a command runs on: a sidebar row, the editor its title-bar button sits on, else the current one
   * (active editor, sidebar selection, the only schema), else one picked from the list. */
  async function schemaDoc(arg: unknown): Promise<vscode.TextDocument | undefined> {
    if (isSchemaArg(arg)) return vscode.workspace.openTextDocument(arg.file);
    if (arg instanceof vscode.Uri) return vscode.workspace.openTextDocument(arg);
    const current = await sidebar.current(true);
    if (current) {
      const active = vscode.window.activeTextEditor?.document;
      return active?.uri.fsPath === current.file ? active : vscode.workspace.openTextDocument(current.file);
    }
    const all = await sidebar.schemas.all();
    if (!all.length) {
      const pick = await vscode.window.showInformationMessage("There's no QuickDBD schema here yet.", "New Schema File");
      if (pick) void vscode.commands.executeCommand("quickdbd.newSchema");
      return undefined;
    }
    const items = all.map((s) => ({ label: targetTitle(s.target), description: vscode.workspace.asRelativePath(s.file), s }));
    const pick = await vscode.window.showQuickPick(items, { title: "Which schema?" });
    return pick && vscode.workspace.openTextDocument(pick.s.file);
  }

  // `opts` comes from a keybinding's or a test's arguments; sidebar rows and menus pass other things, so it's checked.
  const withSchema = (fn: (doc: vscode.TextDocument, opts: Record<string, unknown>) => unknown) => async (arg?: unknown) => {
    const doc = await schemaDoc(arg);
    const plain = arg && typeof arg === "object" && !isSchemaArg(arg) && !(arg instanceof vscode.Uri);
    if (doc) return fn(doc, plain ? { ...arg } : {});
  };
  const str = (v: unknown) => (typeof v === "string" && v ? v : undefined);
  const exporter = (format: Format) =>
    withSchema((doc, opts) => exportDiagram(qdbd, checker, doc, format, str(opts.output)));

  context.subscriptions.push(
    log,
    qdbd,
    checker,
    previews,
    sidebar,
    qdbd.onDidInstall(() => vscode.workspace.textDocuments.forEach((d) => checker.schedule(d, 0))),
    registerSymbols(checker),
    vscode.workspace.onDidOpenTextDocument((doc) => void opened(doc, checker)),
    vscode.workspace.onDidChangeTextDocument((e) => checker.schedule(e.document, TYPING_DELAY)),
    vscode.workspace.onDidSaveTextDocument((doc) => checker.schedule(doc, 0)),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("quickdbd.qdbdPath")) qdbd.reset();
      if (!e.affectsConfiguration("quickdbd")) return;
      vscode.workspace.textDocuments.forEach((d) => checker.schedule(d, 0));
      sidebar.schemas.refresh();
    }),
    vscode.commands.registerCommand("quickdbd.openPreview", withSchema((doc) => previews.show(doc))),
    vscode.commands.registerCommand(
      "quickdbd.openInBrowser",
      withSchema((doc, opts) => previews.browse(doc, opts.open !== false)),
    ),
    vscode.commands.registerCommand("quickdbd.exportPng", exporter("png")),
    vscode.commands.registerCommand("quickdbd.exportSvg", exporter("svg")),
    vscode.commands.registerCommand("quickdbd.exportDrawio", exporter("drawio")),
    vscode.commands.registerCommand("quickdbd.exportHtml", exporter("html")),
    vscode.commands.registerCommand(
      "quickdbd.export",
      withSchema(async (doc) => {
        const formats: { label: string; format: Format }[] = [
          { label: "PNG image", format: "png" },
          { label: "SVG image", format: "svg" },
          { label: "draw.io diagram", format: "drawio" },
          { label: "HTML page", format: "html" },
        ];
        const pick = await vscode.window.showQuickPick(formats, { title: "Export as" });
        if (pick) await exportDiagram(qdbd, checker, doc, pick.format);
      }),
    ),
    vscode.commands.registerCommand("quickdbd.share", withSchema((doc) => share(qdbd, checker, doc))),
    vscode.commands.registerCommand(
      "quickdbd.convertToDbml",
      withSchema((doc, opts) => convertSchema(qdbd, checker, doc, "dbml", log, str(opts.output))),
    ),
    vscode.commands.registerCommand(
      "quickdbd.convertToQuickdbd",
      withSchema((doc, opts) => convertSchema(qdbd, checker, doc, "quickdbd", log, str(opts.output))),
    ),
    vscode.commands.registerCommand(
      "quickdbd.compare",
      withSchema(async (doc, opts) => {
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
    vscode.commands.registerCommand("quickdbd.refreshSchemas", () => sidebar.schemas.refresh()),
    vscode.commands.registerCommand("quickdbd.newSchema", (opts?: { output?: string }) => newSchema(previews, str(opts?.output))),
    // A table's row in the sidebar: open the diagram, then put the cursor in the table, which the diagram follows.
    vscode.commands.registerCommand("quickdbd.revealTable", async (n?: Node) => {
      if (n?.kind !== "table") return;
      const doc = await vscode.workspace.openTextDocument(n.file);
      const at = new vscode.Position(n.table.line - 1, 0);
      await vscode.window.showTextDocument(doc, { selection: new vscode.Range(at, at), preserveFocus: true });
      await previews.show(doc);
    }),
  );
  vscode.workspace.textDocuments.forEach((doc) => void opened(doc, checker));

  return {
    async schemas() {
      return (await sidebar.schemas.all()).map((s) => ({
        ...s,
        title: targetTitle(s.target),
        tables: checker.reportOf(s.target)?.tables?.length,
      }));
    },
  };
}

/** Switch a plain .txt that is a QuickDBD or DBML schema to that language, then check it. */
async function opened(doc: vscode.TextDocument, checker: Checker): Promise<void> {
  if (doc.languageId === "plaintext" && doc.uri.scheme === "file" && /\.txt$/i.test(doc.uri.fsPath)) {
    if (!vscode.workspace.getConfiguration("quickdbd").get<boolean>("autoDetect", true)) return;
    const language = schemaLanguage(doc.uri.fsPath, doc.getText(), true);
    if (!language) return;
    await vscode.languages.setTextDocumentLanguage(doc, language); // reopens it as a schema, which lands here again
    return;
  }
  checker.schedule(doc, 0);
}

/** New Schema File: a small starter schema, opened with its diagram. `output` skips the save dialog (tests). */
async function newSchema(previews: Previews, output?: string): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? os.homedir();
  const out = output
    ? vscode.Uri.file(path.resolve(folder, output))
    : await vscode.window.showSaveDialog({
        title: "New Schema File",
        defaultUri: vscode.Uri.file(path.join(folder, "schema.txt")),
        filters: { "QuickDBD schema": ["txt"] },
      });
  if (!out) return;
  fs.mkdirSync(path.dirname(out.fsPath), { recursive: true });
  fs.writeFileSync(out.fsPath, STARTER); // the save dialog has already asked about replacing a file
  let doc = await vscode.workspace.openTextDocument(out);
  if (doc.languageId !== LANGUAGE) doc = await vscode.languages.setTextDocumentLanguage(doc, LANGUAGE);
  await vscode.window.showTextDocument(doc);
  await previews.show(doc);
}

export function deactivate(): void {}
