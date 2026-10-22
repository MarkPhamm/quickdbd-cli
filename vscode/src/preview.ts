/* The diagram beside the editor: `qdbd serve --embed` per schema, shown in a webview through an iframe.
 * The page (viewer.js, embed mode) and the extension talk through postMessage, relayed by the webview:
 *   page -> extension: qdbd.ready, qdbd.reveal {file, line}
 *   extension -> page: qdbd.focus {table}, qdbd.theme {theme} */
import type { ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Checker } from "./checker.ts";
import type { Qdbd } from "./cli.ts";
import { firstUrl, tableAt, targetKey, type Target } from "./schema.ts";

interface Preview {
  target: Target;
  panel: vscode.WebviewPanel;
  proc: ChildProcess;
  focused?: string;
}

export class Previews implements vscode.Disposable {
  private readonly open = new Map<string, Preview>();
  private readonly starting = new Set<string>();
  private readonly subs: vscode.Disposable[] = [];

  private readonly qdbd: Qdbd;
  private readonly checker: Checker;
  private readonly log: vscode.OutputChannel;

  constructor(qdbd: Qdbd, checker: Checker, log: vscode.OutputChannel) {
    this.qdbd = qdbd;
    this.checker = checker;
    this.log = log;
    this.subs.push(
      vscode.window.onDidChangeActiveColorTheme(() => {
        for (const p of this.open.values()) void p.panel.webview.postMessage({ type: "qdbd.theme", theme: themeKind() });
      }),
      vscode.window.onDidChangeTextEditorSelection((e) => this.follow(e.textEditor)),
      checker.onDidUpdate(() => {
        const ed = vscode.window.activeTextEditor;
        if (ed) this.follow(ed);
      }),
    );
  }

  async show(doc: vscode.TextDocument): Promise<void> {
    const target = this.checker.targetFor(doc);
    const key = targetKey(target);
    const existing = this.open.get(key);
    if (existing) {
      existing.panel.reveal(vscode.ViewColumn.Beside, true);
      return;
    }
    if (this.starting.has(key)) return;
    this.starting.add(key);
    try {
      await this.create(target, key);
    } finally {
      this.starting.delete(key);
    }
  }

  private async create(target: Target, key: string): Promise<void> {
    const proc = await this.qdbd.start(["serve", "--embed", "--port", "0", "--no-open", ...target.paths], target.cwd);
    if (!proc) return;
    const url = await serverUrl(proc, this.log);
    if (!url) {
      proc.kill();
      void vscode.window.showErrorMessage("qdbd serve didn't start; see Output → QuickDBD.");
      return;
    }
    const external = await vscode.env.asExternalUri(vscode.Uri.parse(url));
    const title = "ERD: " + (target.paths[0] === "." ? path.basename(target.cwd) : target.paths[0]);
    const panel = vscode.window.createWebviewPanel(
      "quickdbd.preview",
      title,
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
      { enableScripts: true, retainContextWhenHidden: true },
    );
    const p: Preview = { target, panel, proc };
    this.open.set(key, p);
    panel.webview.html = page(external.toString(true), panel.webview.cspSource);
    panel.webview.onDidReceiveMessage((m: { type?: string; file?: string; line?: number }) => {
      if (m.type === "qdbd.ready") {
        p.focused = undefined;
        void panel.webview.postMessage({ type: "qdbd.theme", theme: themeKind() });
        const ed = vscode.window.activeTextEditor;
        if (ed) this.follow(ed);
      } else if (m.type === "qdbd.reveal" && typeof m.file === "string") {
        const file = path.resolve(target.cwd, m.file);
        if (!path.relative(target.cwd, file).startsWith("..")) void reveal(file, m.line ?? 1);
      }
    });
    panel.onDidDispose(() => {
      this.open.delete(key);
      proc.kill();
    });
    proc.on("exit", (code) => {
      if (this.open.get(key) === p) {
        void vscode.window.showErrorMessage(`qdbd serve stopped (exit ${code}); see Output → QuickDBD.`);
        panel.dispose();
      }
    });
  }

  /** Cursor in a table -> select it in that schema's preview. */
  private follow(ed: vscode.TextEditor): void {
    if (!this.open.size) return;
    const r = this.checker.reportFor(ed.document);
    const p = r && this.open.get(targetKey(r.target));
    if (!r || !p) return;
    const t = tableAt(r.report, r.file, ed.selection.active.line + 1);
    if (!t || t.name === p.focused) return;
    p.focused = t.name;
    void p.panel.webview.postMessage({ type: "qdbd.focus", table: t.name });
  }

  dispose(): void {
    for (const p of this.open.values()) {
      p.proc.kill();
      p.panel.dispose();
    }
    this.subs.forEach((s) => s.dispose());
  }
}

export function themeKind(): "dark" | "light" {
  const k = vscode.window.activeColorTheme.kind;
  return k === vscode.ColorThemeKind.Light || k === vscode.ColorThemeKind.HighContrastLight ? "light" : "dark";
}

async function reveal(file: string, line: number): Promise<void> {
  const doc = await vscode.workspace.openTextDocument(file);
  const pos = new vscode.Position(Math.max(0, line - 1), 0);
  const column = vscode.window.visibleTextEditors.find((e) => e.document.uri.fsPath === file)?.viewColumn;
  await vscode.window.showTextDocument(doc, {
    viewColumn: column ?? vscode.ViewColumn.One,
    selection: new vscode.Range(pos, pos),
  });
}

/** Wait for `qdbd serve`'s "serving … at http://127.0.0.1:PORT/" line. */
function serverUrl(proc: ChildProcess, log: vscode.OutputChannel): Promise<string | undefined> {
  return new Promise((resolve) => {
    let out = "";
    const timer = setTimeout(() => resolve(undefined), 30000);
    const onData = (b: Buffer) => {
      const text = b.toString();
      log.append(text);
      out += text;
      const url = firstUrl(out);
      if (url) {
        clearTimeout(timer);
        resolve(url);
      }
    };
    proc.stdout?.on("data", onData);
    proc.stderr?.on("data", (b: Buffer) => log.append(b.toString()));
    proc.on("error", (e) => {
      log.appendLine(e.message);
      resolve(undefined);
    });
    proc.on("exit", () => resolve(firstUrl(out)));
  });
}

function page(url: string, cspSource: string): string {
  const src = new URL(url);
  src.searchParams.set("theme", themeKind());
  const nonce = randomBytes(16).toString("base64");
  const csp = [
    "default-src 'none'",
    `frame-src ${src.origin}`,
    `style-src ${cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}'`,
  ].join("; ");
  return `<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<style>html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; } iframe { border: 0; width: 100%; height: 100%; display: block; }</style>
</head><body>
<iframe id="erd" src="${src.toString()}" title="ER diagram"></iframe>
<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const frame = document.getElementById("erd");
  window.addEventListener("message", (ev) => {
    const m = ev.data;
    if (!m || typeof m.type !== "string" || !m.type.startsWith("qdbd.")) return;
    if (ev.source === frame.contentWindow) vscode.postMessage(m);
    else frame.contentWindow.postMessage(m, ${JSON.stringify(src.origin)});
  });
</script>
</body></html>`;
}
