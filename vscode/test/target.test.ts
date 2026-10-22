import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { findTarget } from "../src/target.ts";

const TABLE = "Customer\n-\nCustomerId PK int\n";

function tree(files: Record<string, string>): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "qdbd-target-"));
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}

test("a file with its own layout sidecar is a one-file project", () => {
  const root = tree({ "shop.txt": TABLE, "shop.layout.json": "{}", "other.txt": TABLE });
  assert.deepEqual(findTarget(path.join(root, "shop.txt"), root), { cwd: root, paths: ["shop.txt"] });
});

test("the nearest qdbd.layout.json marks the schema folder", () => {
  const root = tree({ "erd/qdbd.layout.json": "{}", "erd/sales/orders.txt": TABLE, "notes.txt": "hello" });
  const erd = path.join(root, "erd");
  assert.deepEqual(findTarget(path.join(erd, "sales", "orders.txt"), root), { cwd: erd, paths: ["."] });
});

test("never looks above the workspace folder", () => {
  const root = tree({ "qdbd.layout.json": "{}", "ws/a.txt": TABLE, "ws/notes.txt": "hello" });
  const ws = path.join(root, "ws");
  assert.deepEqual(findTarget(path.join(ws, "a.txt"), ws), { cwd: ws, paths: ["a.txt"] });
});

test("a folder of schemas is one project; a stray text file keeps it to one file", () => {
  const all = tree({ "a.txt": TABLE, "b.txt": TABLE, "empty.txt": "" });
  assert.deepEqual(findTarget(path.join(all, "a.txt"), all), { cwd: all, paths: ["."] });
  const mixed = tree({ "a.txt": TABLE, "requirements.txt": "flask\n" });
  assert.deepEqual(findTarget(path.join(mixed, "a.txt"), mixed), { cwd: mixed, paths: ["a.txt"] });
});
