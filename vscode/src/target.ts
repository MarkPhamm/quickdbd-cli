/* Which files a schema file belongs with, following the CLI's own conventions (`layout.default_sidecar`):
 * `shop.txt` with `shop.layout.json` is a one-file project; a folder with `qdbd.layout.json` is a multi-file one. */
import * as fs from "node:fs";
import * as path from "node:path";
import { hasTable, type Target } from "./schema.ts";

const MAX_SCAN = 500;

/**
 * 1. `<stem>.layout.json` next to the file: just that file.
 * 2. `qdbd.layout.json` in its folder or a parent (up to `stopAt`): that folder.
 * 3. Every .txt under the file's folder has a table, and no layout file below marks a separate project: the folder
 *    (FKs can point across files).
 * 4. Otherwise just the file, so a stray notes.txt, or a project in a subfolder, doesn't get mixed in.
 */
export function findTarget(file: string, stopAt?: string): Target {
  const dir = path.dirname(file);
  const base = path.basename(file);
  if (fs.existsSync(path.join(dir, base.replace(/\.txt$/i, "") + ".layout.json"))) return { cwd: dir, paths: [base] };
  const top = stopAt ? path.resolve(stopAt) : dir;
  for (let d = dir; ; d = path.dirname(d)) {
    if (fs.existsSync(path.join(d, "qdbd.layout.json"))) return { cwd: d, paths: ["."] };
    if (d === top || path.dirname(d) === d || !d.startsWith(top)) break;
  }
  return allSchemas(dir) ? { cwd: dir, paths: ["."] } : { cwd: dir, paths: [base] };
}

function allSchemas(dir: string): boolean {
  let seen = 0;
  const walk = (d: string): boolean => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) {
        if (e.name.startsWith(".") || e.name === "node_modules" || !walk(p)) return false;
      } else if (e.isFile() && e.name.toLowerCase().endsWith(".layout.json")) {
        return false; // a project of its own (rule 1 or 2 for its files), so this folder isn't one schema
      } else if (e.isFile() && e.name.toLowerCase().endsWith(".txt")) {
        if (++seen > MAX_SCAN) return false;
        const text = fs.readFileSync(p, "utf8");
        if (text.trim() && !hasTable(text)) return false;
      }
    }
    return true;
  };
  return walk(dir);
}
