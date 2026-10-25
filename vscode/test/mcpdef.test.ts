import assert from "node:assert/strict";
import { test } from "node:test";
import { canServe, serverDefs } from "../src/mcpdef.ts";

test("one server per folder with a schema, labelled by folder only when there are several", () => {
  assert.deepEqual(serverDefs([{ name: "shop", fsPath: "/w/shop" }]), [
    { label: "QuickDBD", command: "qdbd", args: ["mcp", "--root", "/w/shop"], cwd: "/w/shop" },
  ]);
  const two = serverDefs([{ name: "a", fsPath: "/a" }, { name: "b", fsPath: "/b" }], "/venv/bin/qdbd");
  assert.deepEqual(two.map((d) => [d.label, d.command]), [["QuickDBD (a)", "/venv/bin/qdbd"], ["QuickDBD (b)", "/venv/bin/qdbd"]]);
  assert.deepEqual(serverDefs([]), []);
});

test("qdbd mcp needs qdbd 0.3.0 or later", () => {
  assert.ok(canServe([0, 3, 0]));
  assert.ok(canServe([1, 0, 0]));
  assert.ok(!canServe([0, 2, 9]));
});
