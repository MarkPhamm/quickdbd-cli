import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { findTarget, isSchemaFile, schemaLanguage } from "../src/target.ts";

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

test("a folder holding other projects isn't one schema", () => {
  // examples/: a standalone sample next to synthetic/, a separate project with its own layout file.
  const nested = tree({ "sample.txt": TABLE, "synthetic/qdbd.layout.json": "{}", "synthetic/a.txt": TABLE });
  assert.deepEqual(findTarget(path.join(nested, "sample.txt"), nested), { cwd: nested, paths: ["sample.txt"] });
  const synthetic = path.join(nested, "synthetic");
  assert.deepEqual(findTarget(path.join(synthetic, "a.txt"), nested), { cwd: synthetic, paths: ["."] });
  // A sibling with its own layout file is a one-file project of its own.
  const sibling = tree({ "a.txt": TABLE, "b.txt": TABLE, "b.layout.json": "{}" });
  assert.deepEqual(findTarget(path.join(sibling, "a.txt"), sibling), { cwd: sibling, paths: ["a.txt"] });
});

test("schema files: a sidecar always counts; content only with auto-detect on", () => {
  const root = tree({ "shop.txt": TABLE, "shop.layout.json": "{}", "notes.txt": "hello", "keyed.txt": TABLE });
  assert.ok(isSchemaFile(path.join(root, "shop.txt"), "anything", false));
  assert.ok(isSchemaFile(path.join(root, "keyed.txt"), TABLE, true));
  assert.ok(!isSchemaFile(path.join(root, "keyed.txt"), TABLE, false));
  assert.ok(!isSchemaFile(path.join(root, "notes.txt"), "hello", true));
});

const DBML = "Table guests {\n  id int [pk]\n}\n";

test("schemaLanguage: .dbml files, DBML in a .txt, QuickDBD, or neither", () => {
  const root = tree({ "a.dbml": "", "b.txt": DBML, "c.txt": TABLE + "x int FK >- Customer.CustomerId\n", "notes.txt": "hi" });
  assert.equal(schemaLanguage(path.join(root, "a.dbml"), "", false), "dbml");
  assert.equal(schemaLanguage(path.join(root, "b.txt"), DBML, true), "dbml");
  assert.equal(schemaLanguage(path.join(root, "c.txt"), TABLE + "x int FK >- Customer.CustomerId\n", true), "quickdbd");
  assert.equal(schemaLanguage(path.join(root, "notes.txt"), "hi", true), null);
  assert.equal(schemaLanguage(path.join(root, "b.txt"), DBML, false), null);
  assert.ok(isSchemaFile(path.join(root, "b.txt"), DBML, true));
});

test("a folder mixing QuickDBD and DBML files is one project", () => {
  const root = tree({ "a.txt": TABLE, "b.dbml": DBML, "c.txt": DBML });
  assert.deepEqual(findTarget(path.join(root, "b.dbml"), root), { cwd: root, paths: ["."] });
  assert.deepEqual(findTarget(path.join(root, "a.txt"), root), { cwd: root, paths: ["."] });
});

test("a .dbml file with its own layout sidecar is a one-file project", () => {
  const root = tree({ "shop.dbml": DBML, "shop.layout.json": "{}", "other.txt": TABLE });
  assert.deepEqual(findTarget(path.join(root, "shop.dbml"), root), { cwd: root, paths: ["shop.dbml"] });
});
