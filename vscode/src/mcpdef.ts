/* The MCP server definitions the extension offers AI chat (Copilot agent mode): `qdbd mcp --root <folder>` for each
 * workspace folder with a schema. No vscode import, so `node --test` runs it. */
import { atLeast } from "./schema.ts";

/** `qdbd mcp` first shipped in qdbd 0.3.0; other features keep working with older ones (cli.ts MIN_VERSION). */
export const MCP_MIN_VERSION = [0, 3, 0];

export interface Folder {
  name: string;
  fsPath: string;
}

export interface ServerDef {
  label: string;
  command: string;
  args: string[];
  cwd: string;
}

/** One server per folder; the label names the folder only when there are several. */
export function serverDefs(folders: Folder[], command = "qdbd"): ServerDef[] {
  return folders.map((f) => ({
    label: folders.length > 1 ? `QuickDBD (${f.name})` : "QuickDBD",
    command,
    args: ["mcp", "--root", f.fsPath],
    cwd: f.fsPath,
  }));
}

export function canServe(version: number[]): boolean {
  return atLeast(version, MCP_MIN_VERSION);
}
