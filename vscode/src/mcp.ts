/* AI chat (Copilot agent mode) gets the schema tools of `qdbd mcp` with no setup: the extension offers one MCP server
 * per workspace folder that has a schema. The API arrived in VS Code 1.101; on older editors (and forks without it)
 * this does nothing, so the extension's engines floor stays where it is. */
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Qdbd } from "./cli.ts";
import { MCP_MIN_VERSION, canServe, serverDefs, type Folder } from "./mcpdef.ts";
import { EXCLUDE, MAX_BYTES } from "./sidebar.ts";
import { isSchemaFile } from "./target.ts";

// The parts of VS Code's MCP API used here, typed locally: @types/vscode stays at the engines floor (1.85).
interface McpStdioDef {
  label: string;
  command: string;
  args: string[];
  cwd?: vscode.Uri;
}
type McpStdioCtor = new (label: string, command: string, args: string[], env: Record<string, string>, version?: string) => McpStdioDef;
interface McpProvider {
  onDidChangeMcpServerDefinitions?: vscode.Event<void>;
  provideMcpServerDefinitions(token: vscode.CancellationToken): Promise<McpStdioDef[]>;
  resolveMcpServerDefinition(server: McpStdioDef, token: vscode.CancellationToken): Promise<McpStdioDef | undefined>;
}
interface McpLm {
  registerMcpServerDefinitionProvider(id: string, provider: McpProvider): vscode.Disposable;
}

const SCAN_CAP = 2000;
const REFRESH_DELAY = 1000;

/** Workspace folders holding a schema file (the sidebar's test) or a dbt project with a manifest. No qdbd runs. */
export async function schemaFolders(): Promise<Folder[]> {
  const auto = vscode.workspace.getConfiguration("quickdbd").get<boolean>("autoDetect", true);
  const out: Folder[] = [];
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const base = new vscode.RelativePattern(folder, "**/*.{txt,dbml}");
    let found = false;
    for (const uri of await vscode.workspace.findFiles(base, EXCLUDE, SCAN_CAP)) {
      try {
        if (fs.statSync(uri.fsPath).size > MAX_BYTES) continue;
        if (isSchemaFile(uri.fsPath, fs.readFileSync(uri.fsPath, "utf8"), auto)) {
          found = true;
          break;
        }
      } catch {
        continue;
      }
    }
    if (!found) {
      const dbt = new vscode.RelativePattern(folder, "**/dbt_project.yml");
      const projects = await vscode.workspace.findFiles(dbt, "**/{.*,node_modules,dbt_packages}/**", 50);
      found = projects.some((u) => fs.existsSync(path.join(path.dirname(u.fsPath), "target", "manifest.json")));
    }
    if (found) out.push({ name: folder.name, fsPath: folder.uri.fsPath });
  }
  return out;
}

export function registerMcp(qdbd: Qdbd, log: vscode.OutputChannel): vscode.Disposable[] {
  const api = vscode as unknown as { lm?: Partial<McpLm>; McpStdioServerDefinition?: McpStdioCtor };
  const Def = api.McpStdioServerDefinition;
  if (!api.lm?.registerMcpServerDefinitionProvider || !Def) return [];

  const changed = new vscode.EventEmitter<void>();
  let last = "";
  let timer: ReturnType<typeof setTimeout> | undefined;
  // Fires only when the set of folders with schemas changes, so chat doesn't restart servers for nothing.
  const recheck = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const now = JSON.stringify(await schemaFolders());
      if (now !== last) {
        last = now;
        changed.fire();
      }
    }, REFRESH_DELAY);
  };
  let warned = false;

  const provider: McpProvider = {
    onDidChangeMcpServerDefinitions: changed.event,
    // Called eagerly, in any workspace: cheap and silent, no qdbd lookup.
    async provideMcpServerDefinitions() {
      const folders = await schemaFolders();
      last = JSON.stringify(folders);
      return serverDefs(folders).map((d) => {
        const def = new Def(d.label, d.command, d.args, {}, String(vscode.extensions.getExtension("MarkPhamm.quickdbd")?.packageJSON.version ?? ""));
        def.cwd = vscode.Uri.file(d.cwd);
        return def;
      });
    },
    // Called when chat starts the server: find qdbd (this may offer to install it) and check it has `mcp`.
    async resolveMcpServerDefinition(server) {
      const found = await qdbd.found();
      if (found && canServe(found.version)) {
        server.command = found.exe;
        return server;
      }
      const need = MCP_MIN_VERSION.join(".");
      log.appendLine(`AI agent tools need qdbd ${need}+; ${found ? `found ${found.version.join(".")}` : "qdbd not found"}`);
      if (found && !warned) {
        warned = true;
        void vscode.window
          .showWarningMessage(`QuickDBD's AI agent tools need qdbd ${need} or later.`, "Update qdbd")
          .then((pick) => pick && qdbd.install());
      }
      return undefined;
    },
  };

  const watchers = ["**/*.{txt,dbml}", "**/dbt_project.yml"].map((glob) => {
    const w = vscode.workspace.createFileSystemWatcher(glob, false, true, false);
    w.onDidCreate(recheck);
    w.onDidDelete(recheck);
    return w;
  });
  return [
    changed,
    ...watchers,
    vscode.workspace.onDidChangeWorkspaceFolders(recheck),
    qdbd.onDidInstall(() => changed.fire()),
    api.lm.registerMcpServerDefinitionProvider("quickdbd", provider),
    { dispose: () => clearTimeout(timer) },
  ];
}
