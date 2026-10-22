/* Finding and running the `qdbd` CLI. The extension has no parser of its own: everything goes through qdbd. */
import { execFile, spawn, type ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { atLeast, parseVersion } from "./schema.ts";

export const MIN_VERSION = [0, 1, 16];
const INSTALL = "uv tool install quickdbd-cli";
const UPGRADE = "uv tool upgrade quickdbd-cli";

export interface RunResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

export class Qdbd {
  private resolved: Promise<string | undefined> | undefined;
  private warned = false;

  private readonly log: vscode.OutputChannel;

  constructor(log: vscode.OutputChannel) {
    this.log = log;
  }

  /** Forget the cached executable (the setting changed). */
  reset(): void {
    this.resolved = undefined;
    this.warned = false;
  }

  /** The qdbd executable, checked once: undefined (after telling the user) if missing or too old. */
  exe(): Promise<string | undefined> {
    this.resolved ??= this.resolve();
    return this.resolved;
  }

  private async resolve(): Promise<string | undefined> {
    for (const exe of candidates()) {
      const out = await version(exe);
      if (out === undefined) continue;
      const v = parseVersion(out);
      this.log.appendLine(`using ${exe} (${out.trim()})`);
      if (v && !atLeast(v, MIN_VERSION)) {
        this.tell(`qdbd ${v.join(".")} is too old for this extension (needs ${MIN_VERSION.join(".")}+).`, UPGRADE);
        return undefined;
      }
      return exe;
    }
    this.tell("The qdbd CLI wasn't found. Install it, or set quickdbd.qdbdPath.", INSTALL);
    return undefined;
  }

  private tell(message: string, command: string): void {
    if (this.warned) return;
    this.warned = true;
    void vscode.window.showWarningMessage(message, `Run "${command}"`, "Open Settings").then((pick) => {
      if (pick === "Open Settings") void vscode.commands.executeCommand("workbench.action.openSettings", "quickdbd.qdbdPath");
      else if (pick) {
        const term = vscode.window.createTerminal("qdbd");
        term.show();
        term.sendText(command);
        this.reset();
      }
    });
  }

  async run(args: string[], cwd: string, stdin?: string): Promise<RunResult | undefined> {
    const exe = await this.exe();
    if (!exe) return undefined;
    return new Promise((resolve) => {
      const child = spawn(exe, args, { cwd });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (b: Buffer) => (stdout += b.toString()));
      child.stderr.on("data", (b: Buffer) => (stderr += b.toString()));
      child.on("error", (e) => resolve({ code: null, stdout, stderr: stderr + e.message }));
      child.on("close", (code) => resolve({ code, stdout, stderr }));
      child.stdin.end(stdin ?? "");
    });
  }

  /** A long-running qdbd (serve). */
  async start(args: string[], cwd: string): Promise<ChildProcess | undefined> {
    const exe = await this.exe();
    return exe ? spawn(exe, args, { cwd }) : undefined;
  }
}

/** quickdbd.qdbdPath, then a project virtualenv, then PATH. */
function candidates(): string[] {
  const setting = vscode.workspace.getConfiguration("quickdbd").get<string>("qdbdPath")?.trim();
  if (setting) return [setting];
  const bin = process.platform === "win32" ? path.join("Scripts", "qdbd.exe") : path.join("bin", "qdbd");
  const venvs = (vscode.workspace.workspaceFolders ?? []).flatMap((f) =>
    [".venv", "venv"].map((v) => path.join(f.uri.fsPath, v, bin)),
  );
  return [...venvs.filter((p) => fs.existsSync(p)), "qdbd"];
}

function version(exe: string): Promise<string | undefined> {
  return new Promise((resolve) => {
    execFile(exe, ["--version"], { timeout: 15000 }, (err, stdout) => resolve(err ? undefined : stdout));
  });
}
