/* End-to-end checks inside VS Code (see run.mjs): detection, outline, go-to-definition across files,
 * diagnostics on unsaved edits, the preview panel, HTML export, comparing with a git ref, dbt import, and (with
 * QDBD_TEST_INSTALL) installing qdbd. */
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";

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

  await editor.edit((e) => e.insert(new vscode.Position(doc.lineCount, 0), "\nBroken\n-\nId int FK >- Nope.Id\n"));
  await until("error for the unsaved edit", () =>
    vscode.languages.getDiagnostics(doc.uri).find((d) => d.message.includes("Nope")),
  );
  step("diagnostics for unsaved text");
  await vscode.commands.executeCommand("undo");
  await until("error cleared after undo", () => (vscode.languages.getDiagnostics(doc.uri).length === 0 ? true : undefined));
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
  await editor.edit((e) => e.insert(new vscode.Position(doc.lineCount, 0), "\nBroken\n-\nId int FK >- Nowhere.Id\n"));
  await until("error from the installed qdbd", () =>
    vscode.languages.getDiagnostics(doc.uri).find((d) => d.message.includes("Nowhere")),
  120000);
  await vscode.commands.executeCommand("undo");
  step("installed qdbd into the extension's own virtualenv");
}
