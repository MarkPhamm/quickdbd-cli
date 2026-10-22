import assert from "node:assert/strict";
import { test } from "node:test";
import {
  atLeast,
  columnDetail,
  findColumn,
  findTable,
  firstUrl,
  hasTable,
  looksLikeDbml,
  looksLikeQuickdbd,
  parseVersion,
  refAt,
  tableAt,
  tablesByFile,
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

test("column details and tables grouped by file, for the sidebar", () => {
  assert.equal(columnDetail({ name: "Id", line: 1, type: "int", pk: true, fk: false }), "int · PK");
  assert.equal(columnDetail({ name: "CustId", line: 1, type: "int", pk: true, fk: true }), "int · PK, FK");
  assert.equal(columnDetail({ name: "Note", line: 1, type: "string" }), "string");
  assert.equal(columnDetail({ name: "Old", line: 1 }), "", "an older qdbd sends no types");
  const t = (name: string, file: string) => ({ name, aliases: [], file, line: 1, endLine: 2, columns: [] });
  const groups = tablesByFile({ ...REPORT, tables: [t("orders", "b.txt"), t("Zeta", "a.txt"), t("alpha", "a.txt")] });
  assert.deepEqual(
    groups.map((g) => [g.file, g.tables.map((x) => x.name)]),
    [
      ["a.txt", ["alpha", "Zeta"]],
      ["b.txt", ["orders"]],
    ],
  );
});

const DBML = `// Invented
Table guests {
  guest_sk integer [primary key]
}

Table "visits" {
  guest_sk integer [ref: > guests.guest_sk]
}

Ref: visits.guest_sk > guests.guest_sk
`;

test("looksLikeDbml: DBML declarations, but never a QuickDBD schema", () => {
  assert.ok(looksLikeDbml(DBML));
  assert.ok(looksLikeDbml("Ref: a.id > b.id\n"));
  assert.ok(looksLikeDbml('table "my table" as t {\n}\n'));
  assert.ok(looksLikeDbml("Project shop {\n  database_type: 'PostgreSQL'\n}\n"));
  assert.ok(!looksLikeDbml(SCHEMA));
  assert.ok(!looksLikeDbml("Ref\n-\nid PK int\n"));
  assert.ok(!looksLikeDbml("# Table x {\nCustomer\n-\nid PK int\n"));
  assert.ok(!looksLikeDbml("Customer\n-\nTable int\nRef: varchar\n"));
  assert.ok(!looksLikeDbml("/* Table a {\n*/\nCustomer\n-\nid int\n"));
  // A `#` comment ending in `{` stays QuickDBD; one-line tables and a `{` on the next line are DBML.
  assert.ok(!looksLikeDbml("Customer\n-\ntable int # like {\nid PK int\n"));
  assert.ok(!looksLikeDbml("Project # the main one {\n-\nid PK int\n"));
  assert.ok(looksLikeDbml("Table a { id int }\n"));
  assert.ok(looksLikeDbml("Table users\n{\n  id int\n}\n"));
  assert.ok(looksLikeDbml("records users(id, name) {\n  1, 'a'\n}\n"));
  const start = Date.now();
  assert.ok(!looksLikeDbml("Customer\n-\nid PK int\n" + "x int /* never closed\n".repeat(20000)));
  assert.ok(Date.now() - start < 500, "an unclosed /* doesn't make the scan quadratic");
});
