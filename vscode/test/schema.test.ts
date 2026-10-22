import assert from "node:assert/strict";
import { test } from "node:test";
import {
  atLeast,
  findColumn,
  findTable,
  firstUrl,
  hasTable,
  looksLikeQuickdbd,
  parseVersion,
  refAt,
  tableAt,
  type Report,
} from "../src/schema.ts";

const SCHEMA = `# Customers
Customer as c
-
CustomerId PK int
Name string

Order
-
OrderId PK int
CustomerId int FK >- Customer.CustomerId
`;

const REPORT: Report = {
  ok: true,
  errors: 0,
  warnings: 0,
  diagnostics: [],
  tables: [
    { name: "Customer", aliases: ["c"], file: "shop.txt", line: 2, endLine: 5, columns: [{ name: "CustomerId", line: 4 }, { name: "Name", line: 5 }] },
    { name: "dbo.Order Line", aliases: [], file: "more/lines.txt", line: 1, endLine: 3, columns: [{ name: "Line Id", line: 3 }] },
  ],
};

test("detects QuickDBD text", () => {
  assert.ok(looksLikeQuickdbd(SCHEMA));
  assert.ok(looksLikeQuickdbd("OrderLine\nrel >- Product\n---\nQty int\n"));
  assert.ok(!looksLikeQuickdbd("requests==2.31\nflask>=3\n"));
  assert.ok(!looksLikeQuickdbd("Notes\n-----\nsome text\n"), "a heading without keys isn't enough");
  assert.ok(!looksLikeQuickdbd("# PK and FK\nnothing else\n"));
  assert.ok(hasTable("Notes\n-----\nsome text\n"));
  assert.ok(!hasTable("# comment\n---\n"));
});

test("finds the table under a line", () => {
  assert.equal(tableAt(REPORT, "shop.txt", 4)?.name, "Customer");
  assert.equal(tableAt(REPORT, "shop.txt", 2)?.name, "Customer");
  assert.equal(tableAt(REPORT, "shop.txt", 7), undefined);
  assert.equal(tableAt(REPORT, "other.txt", 4), undefined);
});

test("looks tables up by name or alias, exact case first", () => {
  assert.equal(findTable(REPORT, "Customer")?.line, 2);
  assert.equal(findTable(REPORT, "customer")?.line, 2);
  assert.equal(findTable(REPORT, "c")?.name, "Customer");
  assert.equal(findTable(REPORT, "Nope"), undefined);
  assert.equal(findColumn(REPORT.tables![0], "name")?.line, 5);
});

test("reads the reference under the cursor", () => {
  const line = "CustomerId int FK >- Customer.CustomerId  # the buyer";
  assert.deepEqual(refAt(line, line.indexOf("Customer.") + 2), { table: "Customer", column: "CustomerId" });
  assert.deepEqual(refAt(line, line.indexOf(".CustomerId") + 3), { table: "Customer", column: "CustomerId" });
  assert.equal(refAt(line, line.indexOf("buyer")), undefined, "comments aren't references");
  const quoted = 'LineId int FK >- "dbo.Order Line"."Line Id"';
  assert.deepEqual(refAt(quoted, quoted.indexOf("Order")), { table: "dbo.Order Line", column: "Line Id" });
  assert.deepEqual(refAt("rel >- Product", 9), { table: "Product" });
});

test("versions and URLs", () => {
  assert.deepEqual(parseVersion("qdbd 0.1.16\n"), [0, 1, 16]);
  assert.equal(parseVersion("command not found"), undefined);
  assert.ok(atLeast([0, 1, 16], [0, 1, 16]));
  assert.ok(atLeast([0, 2, 0], [0, 1, 16]));
  assert.ok(!atLeast([0, 1, 9], [0, 1, 16]));
  assert.equal(firstUrl("[qdbd] serving 3 file(s) at http://127.0.0.1:54321/  (layout: x)"), "http://127.0.0.1:54321/");
});
