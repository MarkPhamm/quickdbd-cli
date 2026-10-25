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

// The findTarget cases live in tests/fixtures/targets/cases.json, so the Python port (targets.py) runs the same ones.
interface Case {
  name: string;
  files: Record<string, string>;
  file: string;
  stopAt?: string;
  expect: { cwd: string; paths: string[] };
}
const CASES: Case[] = JSON.parse(
  fs.readFileSync(path.join(import.meta.dirname, "..", "..", "tests", "fixtures", "targets", "cases.json"), "utf8"),
);

for (const c of CASES) {
  test(c.name, () => {
    const root = tree(c.files);
    assert.deepEqual(findTarget(path.join(root, c.file), path.join(root, c.stopAt ?? "")), {
      cwd: path.join(root, c.expect.cwd),
      paths: c.expect.paths,
    });
  });
}

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
