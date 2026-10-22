/* Convert to DBML / Convert to QuickDBD Syntax: `qdbd convert` on the schema a file belongs to. A one-file schema is
 * written next to it (or where the save dialog says); a folder schema into a sibling folder, since writing the converted
 * files into the same folder would define every table twice. */
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Checker } from "./checker.ts";
import type { Qdbd } from "./cli.ts";
import { targetTitle } from "./target.ts";

export type Syntax = "dbml" | "quickdbd";

const EXT: Record<Syntax, string> = { dbml: ".dbml", quickdbd: ".txt" };
const NAME: Record<Syntax, string> = { dbml: "DBML", quickdbd: "QuickDBD" };

/** `output` (a path, relative to the schema's folder) skips the questions, for keybindings and tests. */
export async function convertSchema(
  qdbd: Qdbd,
  checker: Checker,
  doc: vscode.TextDocument,
  to: Syntax,
  log: vscode.OutputChannel,
  output?: string,
): Promise<vscode.Uri | undefined> {
  const target = checker.targetFor(doc);
  const folder = target.paths[0] === ".";
  let out: string | undefined;
  if (output) {
    out = path.resolve(target.cwd, output);
  } else if (folder) {
    const suggested = `${target.cwd}-${to}`;
    const pick = await vscode.window.showInformationMessage(
      `Convert the ${targetTitle(target)} schema to ${NAME[to]} in ${path.basename(suggested)}/?`,
      { modal: true, detail: "The converted files go into a new folder next to this one." },
      "Convert",
    );
    out = pick ? suggested : undefined;
  } else {
    const stem = path.parse(target.paths[0]).name;
    out = (
      await vscode.window.showSaveDialog({
        defaultUri: vscode.Uri.file(path.join(target.cwd, stem + EXT[to])),
        filters: { [`${NAME[to]} schema`]: [EXT[to].slice(1)] },
      })
    )?.fsPath;
  }
  if (!out) return undefined;
  const args = ["convert", ...target.paths, "--to", to, "-o", out];
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Converting to ${NAME[to]}…` },
    () => qdbd.run(args, target.cwd),
  );
  if (!res) return undefined;
  if (res.code !== 0) {
    void vscode.window.showErrorMessage(`qdbd convert failed: ${(res.stderr || res.stdout).trim()}`);
    return undefined;
  }
  const warnings = res.stderr.split(/\r?\n/).filter((l) => l.includes(": warning: "));
  if (warnings.length) {
    log.appendLine(`qdbd ${args.join(" ")}:\n${warnings.join("\n")}`);
    void vscode.window
      .showWarningMessage(`Converted, with ${warnings.length} thing(s) ${NAME[to]} can't express.`, "Show")
      .then((pick) => pick && log.show());
  }
  const file = folder ? firstSchema(out) : out;
  if (!file) return undefined;
  const uri = vscode.Uri.file(file);
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(uri));
  return uri;
}

function firstSchema(dir: string): string | undefined {
  const names = fs.readdirSync(dir).filter((n) => /\.(txt|dbml)$/i.test(n)).sort();
  return names.length ? path.join(dir, names[0]) : undefined;
}
