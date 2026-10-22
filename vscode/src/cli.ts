/* Finding, running and installing the `qdbd` CLI. The extension has no parser of its own: everything goes through qdbd.
 * When it's missing or too old, the extension installs it into a virtualenv of its own (venv.ts): no terminal needed. */
import { execFile, spawn, type ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { atLeast, parseVersion } from "./schema.ts";
import { installPlan, venvBin, type ExecResult } from "./venv.ts";

export const MIN_VERSION = [0, 1, 17];

export type RunResult = ExecResult;

interface Found {
  exe: string;
  version: number[];
}

export class Qdbd {
  private resolved: Promise<Found | undefined> | undefined;
  private warned = false;
  private installing: Promise<boolean> | undefined;
  private readonly installed = new vscode.EventEmitter<void>();
  /** Fires after an install or update, so checks that failed for want of qdbd can run again. */
  readonly onDidInstall = this.installed.event;

  private readonly log: vscode.OutputChannel;
  private readonly venv: string;

  constructor(log: vscode.OutputChannel, storage: string) {
    this.log = log;
    this.venv = path.join(storage, "qdbd-venv");
  }

  /** Forget the cached executable (the setting changed, or qdbd was installed). */
  reset(): void {
    this.resolved = undefined;
    this.warned = false;
  }

  /** The qdbd executable, checked once: undefined (after telling the user) if missing or too old. */
  exe(): Promise<string | undefined> {
    return this.found().then((f) => f?.exe);
  }

  private found(): Promise<Found | undefined> {
    this.resolved ??= this.resolve();
    return this.resolved;
  }

  /**
   * 1. The quickdbd.qdbdPath setting, if set: only that.
   * 2. The workspace's .venv (or venv): the project's own pin.
   * 3. Otherwise the extension's own install or the one on PATH, whichever is newer.
   */
  private async resolve(): Promise<Found | undefined> {
    let old: string | undefined;
    const probe = async (exe: string): Promise<Found | undefined> => {
      const out = await version(exe);
      if (out === undefined) return undefined;
      const v = parseVersion(out) ?? MIN_VERSION;
      if (!atLeast(v, MIN_VERSION)) {
        this.log.appendLine(`skipping ${exe} (${out.trim()}): needs ${MIN_VERSION.join(".")}+`);
        old ??= v.join(".");
        return undefined;
      }
      return { exe, version: v };
    };
    const use = (f: Found) => {
      this.log.appendLine(`using ${f.exe} (qdbd ${f.version.join(".")})`);
      return f;
    };
    const setting = vscode.workspace.getConfiguration("quickdbd").get<string>("qdbdPath")?.trim();
    if (setting) {
      const f = await probe(setting);
      if (f) return use(f);
      this.tell(
        old
          ? `quickdbd.qdbdPath points to qdbd ${old}, which is too old for this extension (needs ${MIN_VERSION.join(".")}+).`
          : `quickdbd.qdbdPath (${setting}) didn't run.`,
      );
      return undefined;
    }
    for (const exe of workspaceVenvs()) {
      const f = await probe(exe);
      if (f) return use(f);
    }
    const found = (await Promise.all([venvBin(this.venv, "qdbd"), "qdbd"].map(probe))).filter((f) => f !== undefined);
    found.sort((a, b) => (atLeast(a.version, b.version) ? -1 : 1));
    if (found[0]) return use(found[0]);
    this.tell(
      old
        ? `qdbd ${old} is too old for this extension (needs ${MIN_VERSION.join(".")}+).`
        : "QuickDBD runs the qdbd CLI, which isn't installed.",
      old ? "Update qdbd" : "Install qdbd",
    );
    return undefined;
  }

  private tell(message: string, install?: string): void {
    if (this.warned) return;
    this.warned = true;
    const actions = install ? [install, "Open Settings"] : ["Open Settings"];
    void vscode.window.showWarningMessage(message, ...actions).then((pick) => {
      if (pick === "Open Settings") void vscode.commands.executeCommand("workbench.action.openSettings", "quickdbd.qdbdPath");
      else if (pick) void this.install();
    });
  }

  /** Install qdbd, or update it, in the extension's own virtualenv. True when a usable qdbd is ready. */
  install(): Promise<boolean> {
    this.installing ??= this.doInstall().finally(() => (this.installing = undefined));
    return this.installing;
  }

  private async doInstall(): Promise<boolean> {
    const done = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "Installing qdbd" },
      async (progress) => {
        progress.report({ message: "looking for Python…" });
        const plan = await installPlan((cmd, args) => exec(cmd, args), this.venv);
        if (!plan) {
          const pick = await vscode.window.showErrorMessage(
            "Installing qdbd needs Python 3.11 or later, and none was found. Install Python, then try again.",
            "Download Python",
          );
          if (pick) void vscode.env.openExternal(vscode.Uri.parse("https://www.python.org/downloads/"));
          return false;
        }
        try {
          fs.rmSync(this.venv, { recursive: true, force: true });
        } catch (e) {
          void vscode.window.showErrorMessage(`Couldn't replace the old install (close the diagrams and retry): ${e}`);
          return false;
        }
        const steps = ["creating a Python environment…", "downloading quickdbd-cli…"];
        for (const [i, [cmd, ...args]] of plan.entries()) {
          progress.report({ message: steps[i] });
          this.log.appendLine(`$ ${[cmd, ...args].join(" ")}`);
          const r = await exec(cmd, args, { log: this.log });
          if (r.code !== 0) {
            const why = (r.stderr || r.stdout).trim().split("\n").pop();
            const pick = await vscode.window.showErrorMessage(`Installing qdbd failed: ${why}`, "Show Output");
            if (pick) this.log.show();
            return false;
          }
        }
        return true;
      },
    );
    if (!done) return false;
    this.reset();
    const found = await this.found();
    if (!found) return false;
    void vscode.window.showInformationMessage(`qdbd ${found.version.join(".")} is ready.`);
    this.installed.fire();
    return true;
  }

  run(args: string[], cwd: string, stdin?: string): Promise<RunResult | undefined> {
    return this.exe().then((exe) => (exe ? exec(exe, args, { cwd, stdin }) : undefined));
  }

  /** A long-running qdbd (serve). */
  async start(args: string[], cwd: string): Promise<ChildProcess | undefined> {
    const exe = await this.exe();
    return exe ? spawn(exe, args, { cwd }) : undefined;
  }

  dispose(): void {
    this.installed.dispose();
  }
}

function exec(
  cmd: string,
  args: string[],
  opts: { cwd?: string; stdin?: string; log?: vscode.OutputChannel } = {},
): Promise<RunResult> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { cwd: opts.cwd });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b: Buffer) => {
      stdout += b.toString();
      opts.log?.append(b.toString());
    });
    child.stderr.on("data", (b: Buffer) => {
      stderr += b.toString();
      opts.log?.append(b.toString());
    });
    child.on("error", (e) => resolve({ code: null, stdout, stderr: stderr + e.message }));
    child.on("close", (code) => resolve({ code, stdout, stderr }));
    child.stdin.on("error", () => undefined); // a command that exits before reading stdin
    child.stdin.end(opts.stdin ?? "");
  });
}

function workspaceVenvs(): string[] {
  return (vscode.workspace.workspaceFolders ?? [])
    .flatMap((f) => [".venv", "venv"].map((v) => venvBin(path.join(f.uri.fsPath, v), "qdbd")))
    .filter((p) => fs.existsSync(p));
}

function version(exe: string): Promise<string | undefined> {
  return new Promise((resolve) => {
    execFile(exe, ["--version"], { timeout: 15000 }, (err, stdout) => resolve(err ? undefined : stdout));
  });
}
