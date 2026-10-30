/* Export PNG / SVG / draw.io / HTML and share as a gist: thin wrappers over `qdbd export` and `qdbd build`. Sharing
 * signs in with VS Code's GitHub account (gist.ts), so it needs neither the gh CLI nor a terminal. */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Checker } from "./checker.ts";
import type { Qdbd } from "./cli.ts";
import { githubApi, publish, shareKey } from "./gist.ts";
import { atLeast, firstUrl, tableAt, type Target } from "./schema.ts";
import { targetTitle } from "./target.ts";

const FORMATS = { png: "PNG image", svg: "SVG image", drawio: "draw.io diagram", html: "HTML page" } as const;
export type Format = keyof typeof FORMATS;

/** `output` (a path) skips the questions, for keybindings and tests. */
export async function exportDiagram(
  qdbd: Qdbd,
  checker: Checker,
  doc: vscode.TextDocument,
  format: Format,
  output?: string,
) {
  const target = checker.targetFor(doc);
  const r = checker.reportFor(doc);
  const ed = vscode.window.activeTextEditor;
  // The HTML page is the whole interactive diagram; the images can be one table and its neighbours.
  const here =
    format !== "html" && !output && r && ed?.document === doc
      ? tableAt(r.report, r.file, ed.selection.active.line + 1)
      : undefined;
  let focus: string | undefined;
  if (here) {
    const whole = "Whole diagram";
    const pick = await vscode.window.showQuickPick([whole, `${here.name} and its neighbours`], { title: "Export" });
    if (!pick) return;
    focus = pick === whole ? undefined : here.name;
  }
  const stem = focus ?? targetTitle(target);
  const out = output
    ? vscode.Uri.file(path.resolve(target.cwd, output))
    : await vscode.window.showSaveDialog({
        defaultUri: vscode.Uri.file(path.join(target.cwd, `${stem}.${format}`)),
        filters: { [FORMATS[format]]: [format] },
      });
  if (!out) return;
  const args =
    format === "html"
      ? ["build", ...target.paths, "-o", out.fsPath]
      : ["export", ...target.paths, "-o", out.fsPath, ...(focus ? ["--focus", focus] : [])];
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Exporting ${path.basename(out.fsPath)}…` },
    () => qdbd.run(args, target.cwd),
  );
  if (!res) return;
  if (res.code !== 0) {
    void vscode.window.showErrorMessage(`qdbd ${args[0]} failed: ${(res.stderr || res.stdout).trim()}`);
    return;
  }
  // A page opens in the browser; there's no local browser to open it in from a remote window.
  const action = format === "html" ? (vscode.env.remoteName ? undefined : "Open in Browser") : "Open";
  const open = await vscode.window.showInformationMessage(`Wrote ${path.basename(out.fsPath)}`, ...(action ? [action] : []));
  if (open === "Open") void vscode.commands.executeCommand("vscode.open", out);
  else if (open) void vscode.env.openExternal(out);
}

/** Off by default: a gist puts the schema outside the organisation's control. User settings only (`scope: application`). */
export const sharingAllowed = () => vscode.workspace.getConfiguration("quickdbd").get<boolean>("allowSharing", false);

const DISCLAIMER_URL = "https://qdbd.dev/sharing/#disclaimer";
// Shown before every share; keep in step with DISCLAIMER in share.py.
const DISCLAIMER =
  "This uploads the diagram (every table and column name, type, key, relationship and comment) to a GitHub gist. Anyone with the link can open it, and copies can outlive the gist.\n\n" +
  "By sharing, you confirm that you have the right to publish this schema, that your organisation's policies and any client agreements allow it, and that qdbd's authors are not liable for any disclosure.";

export async function share(qdbd: Qdbd, checker: Checker, doc: vscode.TextDocument) {
  if (!sharingAllowed()) {
    const open = await vscode.window.showWarningMessage(
      "Sharing is off. It uploads the diagram to a GitHub gist that anyone with the link can open. Turn on QuickDBD: Allow Sharing only if your data policy allows that.",
      "Open Settings",
      "Read the Disclaimer",
    );
    if (open === "Open Settings") void vscode.commands.executeCommand("workbench.action.openSettings", "quickdbd.allowSharing");
    else if (open) void vscode.env.openExternal(vscode.Uri.parse(DISCLAIMER_URL));
    return;
  }
  const target = checker.targetFor(doc);
  const pick = await vscode.window.showWarningMessage(
    `Share ${targetTitle(target)} as a secret gist?`,
    { modal: true, detail: DISCLAIMER },
    "Share",
    "Read the Disclaimer",
  );
  if (pick === "Read the Disclaimer") void vscode.env.openExternal(vscode.Uri.parse(DISCLAIMER_URL));
  if (pick !== "Share") return;
  let token: string;
  try {
    token = (await vscode.authentication.getSession("github", ["gist"], { createIfNone: true })).accessToken;
  } catch (e) {
    // An editor without VS Code's GitHub sign-in: `qdbd share` signs in through the gh CLI instead.
    if (/provider/i.test(String(e))) return shareWithGh(qdbd, target);
    return; // sign-in cancelled
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qdbd-share-"));
  try {
    const shared = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "Publishing the diagram as a secret gist…" },
      async () => {
        const page = path.join(dir, "page.html");
        const res = await qdbd.run(["build", ...target.paths, "-o", page], target.cwd);
        if (!res) return undefined;
        if (res.code !== 0) throw new Error((res.stderr || res.stdout).trim());
        return publish(githubApi(token), fs.readFileSync(page, "utf8"), targetTitle(target), shareKey(target));
      },
    );
    if (shared) await copied(shared.link, shared.updated ? "Updated the gist. Link copied" : "Link copied");
  } catch (e) {
    void vscode.window.showErrorMessage(`Sharing failed: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

async function shareWithGh(qdbd: Qdbd, target: Target) {
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Publishing the diagram as a secret gist…" },
    // The setting is the opt-in, and the dialog the confirmation; qdbd 0.4.0+ wants both said again.
    async () => {
      const found = await qdbd.found();
      const yes = found && atLeast(found.version, [0, 4, 0]) ? ["--yes"] : [];
      return qdbd.run(["share", ...yes, ...target.paths], target.cwd, undefined, { QDBD_ALLOW_SHARE: "1" });
    },
  );
  if (!res) return;
  // "Link: <viewer url>" is the one to share; the first URL printed is the gist itself.
  const url = res.code === 0 ? (/^Link:\s*(\S+)/m.exec(res.stdout)?.[1] ?? firstUrl(res.stdout)) : undefined;
  if (!url) {
    void vscode.window.showErrorMessage(`qdbd share failed: ${(res.stderr || res.stdout).trim()}`);
    return;
  }
  await copied(url, "Link copied");
}

async function copied(url: string, what: string) {
  await vscode.env.clipboard.writeText(url);
  const open = await vscode.window.showInformationMessage(`${what}: ${url}`, "Open");
  if (open) void vscode.env.openExternal(vscode.Uri.parse(url));
}
