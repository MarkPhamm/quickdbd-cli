/* Outline, Ctrl+T and F12, all from the last `qdbd check --symbols` report (see checker.ts). */
import * as path from "node:path";
import * as vscode from "vscode";
import { LANGUAGE, type Checker } from "./checker.ts";
import { findColumn, findTable, refAt, type Table, type Target } from "./schema.ts";

function lineRange(line: number): vscode.Range {
  const l = Math.max(0, line - 1);
  return new vscode.Range(l, 0, l, 0);
}

function location(target: Target, file: string, line: number): vscode.Location {
  return new vscode.Location(vscode.Uri.file(path.resolve(target.cwd, file)), lineRange(line));
}

function tableSymbol(t: Table): vscode.DocumentSymbol {
  const range = new vscode.Range(t.line - 1, 0, Math.max(t.line, t.endLine) - 1, Number.MAX_SAFE_INTEGER);
  const detail = t.aliases.length ? "as " + t.aliases.join(", ") : "";
  const sym = new vscode.DocumentSymbol(t.name, detail, vscode.SymbolKind.Struct, range, lineRange(t.line));
  sym.children = t.columns.map((c) => {
    const r = new vscode.Range(c.line - 1, 0, c.line - 1, Number.MAX_SAFE_INTEGER);
    return new vscode.DocumentSymbol(c.name, "", vscode.SymbolKind.Field, r, lineRange(c.line));
  });
  return sym;
}

export function registerSymbols(checker: Checker): vscode.Disposable {
  const selector: vscode.DocumentSelector = { language: LANGUAGE, scheme: "file" };
  return vscode.Disposable.from(
    vscode.languages.registerDocumentSymbolProvider(selector, {
      async provideDocumentSymbols(doc) {
        await checker.ready(doc);
        const r = checker.reportFor(doc);
        return r ? (r.report.tables ?? []).filter((t) => t.file === r.file).map(tableSymbol) : [];
      },
    }),
    vscode.languages.registerWorkspaceSymbolProvider({
      provideWorkspaceSymbols(query) {
        const q = query.toLowerCase();
        return checker.reports().flatMap(({ target, report }) =>
          (report.tables ?? [])
            .filter((t) => t.name.toLowerCase().includes(q))
            .map((t) => new vscode.SymbolInformation(t.name, vscode.SymbolKind.Struct, "", location(target, t.file, t.line))),
        );
      },
    }),
    vscode.languages.registerDefinitionProvider(selector, {
      async provideDefinition(doc, pos) {
        await checker.ready(doc);
        const r = checker.reportFor(doc);
        const ref = r && refAt(doc.lineAt(pos.line).text, pos.character);
        const table = ref && findTable(r.report, ref.table);
        if (!r || !ref || !table) return undefined;
        const col = ref.column ? findColumn(table, ref.column) : undefined;
        return location(r.target, table.file, col ? col.line : table.line);
      },
    }),
  );
}
