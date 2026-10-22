/* End-to-end checks inside VS Code (see run.mjs): detection, outline, go-to-definition across files,
 * diagnostics on unsaved edits, and the preview panel. */
import assert from "node:assert/strict";
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
