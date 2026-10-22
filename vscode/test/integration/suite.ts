/* End-to-end checks inside VS Code (see run.mjs): detection, outline, go-to-definition across files,
 * diagnostics on unsaved edits, the preview panel, HTML export, comparing with a git ref, dbt import, and (with
 * QDBD_TEST_INSTALL) installing qdbd. */
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Api } from "../../src/extension.ts";

async function until<T>(what: string, probe: () => T | undefined | Promise<T | undefined>, ms = 30000): Promise<T> {
  const end = Date.now() + ms;
  for (;;) {
    const v = await probe();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out waiting for: ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

function step(name: string): void {
  console.log(`  ✓ ${name}`);
}

/** Put a document back to `text` and save it. Not the undo command: that acts on the focused editor, and nothing in
 * the test window has focus while another app is in front, so it would quietly do nothing. */
async function restore(editor: vscode.TextEditor, text: string): Promise<void> {
  const doc = editor.document;
  await editor.edit((e) => e.replace(new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length)), text));
  await doc.save();
}

export async function run(): Promise<void> {
  const ws = vscode.workspace.workspaceFolders![0].uri.fsPath;
  const file = path.join(ws, "examples", "synthetic", "finance.txt");
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(file));
  const doc = await until("finance.txt detected as QuickDBD", () =>
    vscode.workspace.textDocuments.find((d) => d.uri.fsPath === file && d.languageId === "quickdbd"),
  );
  const editor = await vscode.window.showTextDocument(doc);
  step("plain .txt detected as QuickDBD");

  const symbols = await until("outline", async () => {
    const s = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>("vscode.executeDocumentSymbolProvider", doc.uri);
    return s?.length ? s : undefined;
  });
  const ledger = symbols.find((s) => s.name === "Ledger");
  assert.ok(ledger && ledger.children.some((c) => c.name === "LedgerId"), "Ledger with its columns");
  step(`outline: ${symbols.length} tables`);

  const local = new Set(symbols.map((s) => s.name));
  const lines = doc.getText().split("\n");
  const at = lines.findIndex((l) => {
    const m = /FK [<>0-]+ (\w+)\./.exec(l);
    return m && !local.has(m[1]);
  });
  assert.ok(at >= 0, "a foreign key into another file");
  const target = /FK [<>0-]+ (\w+)\./.exec(lines[at])!;
  const pos = new vscode.Position(at, lines[at].indexOf(target[1], target.index + 3) + 1);
  const defs = await vscode.commands.executeCommand<(vscode.Location | vscode.LocationLink)[]>(
    "vscode.executeDefinitionProvider",
    doc.uri,
    pos,
  );
  const uri = defs[0] && ("uri" in defs[0] ? defs[0].uri : defs[0].targetUri);
  assert.ok(uri && uri.fsPath !== file, `F12 on ${target[1]} jumps to another file`);
  step(`go to definition: ${target[1]} -> ${path.basename(uri.fsPath)}`);

  const original = doc.getText();
  await editor.edit((e) => e.insert(new vscode.Position(doc.lineCount, 0), "\nBroken\n-\nId int FK >- Nope.Id\n"));
  await until("error for the unsaved edit", () =>
    vscode.languages.getDiagnostics(doc.uri).find((d) => d.message.includes("Nope")),
  );
  step("diagnostics for unsaved text");
  await restore(editor, original);
  await until("error cleared", () => (vscode.languages.getDiagnostics(doc.uri).length === 0 ? true : undefined));
  step("diagnostics cleared");

  // A standalone file next to another project is checked on its own, not merged with it.
  const sample = path.join(ws, "examples", "quickdbd-sample.txt");
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(sample));
  const sampleDoc = await until("quickdbd-sample.txt detected as QuickDBD", () =>
    vscode.workspace.textDocuments.find((d) => d.uri.fsPath === sample && d.languageId === "quickdbd"),
  );
  const sampleSymbols = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
    "vscode.executeDocumentSymbolProvider",
    sampleDoc.uri,
  );
  assert.ok(sampleSymbols?.some((s) => s.name === "Customer"), "the sample's own outline");
  const stray = vscode.languages.getDiagnostics().filter(([, d]) => d.length);
  assert.deepEqual(stray.map(([u, d]) => `${path.basename(u.fsPath)}: ${d[0].message}`), [], "no errors anywhere");
  step(`standalone file next to another project: ${sampleSymbols.length} tables, no errors`);
  await vscode.window.showTextDocument(doc);

  await vscode.commands.executeCommand("quickdbd.openPreview");
  const tab = await until("preview panel", () =>
    vscode.window.tabGroups.all
      .flatMap((g) => g.tabs)
      .find((t) => t.input instanceof vscode.TabInputWebview && t.label.startsWith("ERD")),
  );
  step(`preview opened: ${tab.label}`);

  const webviewTab = (label: string) => () =>
    vscode.window.tabGroups.all
      .flatMap((g) => g.tabs)
      .find((t) => t.input instanceof vscode.TabInputWebview && t.label === label);

  await vscode.window.showTextDocument(doc);
  // Not awaited: the command ends on a "Wrote …" notification that waits to be dismissed.
  void vscode.commands.executeCommand("quickdbd.exportHtml", { output: "synthetic.html" });
  const page = path.join(ws, "examples", "synthetic", "synthetic.html");
  await until("synthetic.html", () => fs.existsSync(page) && fs.readFileSync(page, "utf8").includes('id="qdbd-data"'));
  step("export HTML page");

  await vscode.commands.executeCommand("quickdbd.compare", { ref: "HEAD" });
  await until("compare panel", webviewTab("ERD: synthetic vs HEAD"));
  step("compare with HEAD");

  await vscode.commands.executeCommand("quickdbd.importDbt", {
    manifest: path.join(ws, "jaffle", "target", "manifest.json"),
    output: "erd",
  });
  const imported = fs.readdirSync(path.join(ws, "jaffle", "erd")).filter((f) => f.endsWith(".txt"));
  assert.ok(imported.length > 0, "schema files written");
  await until("imported schema's diagram", webviewTab("ERD: erd"));
  assert.equal(vscode.window.activeTextEditor?.document.languageId, "quickdbd");
  step(`dbt import: ${imported.join(", ")}, opened with its diagram`);

  // The sidebar lists every schema in the workspace, checked, without opening their files.
  const api = vscode.extensions.getExtension("MarkPhamm.quickdbd")!.exports as Api;
  await vscode.commands.executeCommand("workbench.view.extension.quickdbd");
  const listed = await until("sidebar schemas, checked", async () => {
    const all = await api.schemas();
    return ["synthetic", "quickdbd-sample", "erd"].every((t) => all.some((x) => x.title === t && x.tables)) ? all : undefined;
  });
  const hidden = listed.filter((x) => path.relative(ws, x.file).split(path.sep).some((part) => part.startsWith(".")));
  assert.deepEqual(hidden.map((x) => x.file), [], "nothing from hidden folders (.history, .vscode-test, …)");
  step(`sidebar: ${listed.map((x) => `${x.title} (${x.tables} tables)`).join(", ")}`);

  // A schema row's button acts on that schema, not the active editor's.
  const sampleRow = listed.find((x) => x.title === "quickdbd-sample")!;
  await vscode.commands.executeCommand("quickdbd.openPreview", { kind: "schema", target: sampleRow.target, file: sampleRow.file });
  await until("sample diagram from its sidebar row", webviewTab("ERD: quickdbd-sample"));
  step("open diagram from a sidebar row");

  // New Schema File writes a starter, opens it with its diagram, and the sidebar picks it up from the file watcher.
  await vscode.commands.executeCommand("quickdbd.newSchema", { output: "starter/schema.txt" });
  // Alone in its folder, the schema is the folder's: "starter".
  await until("starter's diagram", webviewTab("ERD: starter"));
  await until("starter in the sidebar", async () => (await api.schemas()).some((x) => x.title === "starter" && x.tables === 2));
  step("new schema file: opened with its diagram, listed in the sidebar");

  if (process.env.QDBD_TEST_INSTALL) await testInstall(doc);

  // QDBD_HOLD=ms keeps the window open (cursor on Ledger, so the preview should select it) for a screenshot.
  const hold = Number(process.env.QDBD_HOLD || 0);
  if (hold) {
    for (const cmd of ["workbench.action.closeAuxiliaryBar", "notifications.clearAll"]) {
      await vscode.commands.executeCommand(cmd).then(undefined, () => undefined);
    }
    await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
    const line = new vscode.Position(ledger.selectionRange.start.line + 2, 0);
    vscode.window.activeTextEditor!.selection = new vscode.Selection(line, line);
    await new Promise((r) => setTimeout(r, hold));
  }
}

/** Without quickdbd.qdbdPath, install qdbd (from this checkout, QDBD_PIP_SPEC) into the extension's own virtualenv,
 * then check that errors are reported again. Only meaningful where no new-enough qdbd is on PATH. */
async function testInstall(doc: vscode.TextDocument): Promise<void> {
  await vscode.workspace.getConfiguration("quickdbd").update("qdbdPath", undefined, vscode.ConfigurationTarget.Workspace);
  const ok = await vscode.commands.executeCommand<boolean>("quickdbd.installCli");
  assert.equal(ok, true, "installCli reports success");
  const editor = await vscode.window.showTextDocument(doc);
  const original = doc.getText();
  await editor.edit((e) => e.insert(new vscode.Position(doc.lineCount, 0), "\nBroken\n-\nId int FK >- Nowhere.Id\n"));
  await until("error from the installed qdbd", () =>
    vscode.languages.getDiagnostics(doc.uri).find((d) => d.message.includes("Nowhere")),
  120000);
  await restore(editor, original);
  step("installed qdbd into the extension's own virtualenv");
}
