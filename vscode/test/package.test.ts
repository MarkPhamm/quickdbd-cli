import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { test } from "node:test";

const root = path.join(import.meta.dirname, "..");

/** `.vscodeignore` ignores everything (`**`) and lists what ships with `!`; a file shipped by `!dir/**` counts. */
function shipped(file: string): boolean {
  const rules = fs
    .readFileSync(path.join(root, ".vscodeignore"), "utf8")
    .split(/\r?\n/)
    .filter((l) => l.startsWith("!"))
    .map((l) => l.slice(1).trim());
  return rules.some((r) => r === file || (r.endsWith("/**") && file.startsWith(r.slice(0, -2))));
}

test("every file package.json points at ships in the .vsix", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  const c = pkg.contributes;
  const files: string[] = [
    pkg.main,
    pkg.icon,
    ...c.languages.flatMap((l: { configuration?: string }) => (l.configuration ? [l.configuration] : [])),
    ...c.grammars.map((g: { path: string }) => g.path),
    ...c.viewsContainers.activitybar.map((v: { icon: string }) => v.icon),
  ]
    .filter(Boolean)
    .map((f) => path.normalize(f).replace(/\\/g, "/"));
  for (const f of files) {
    assert.ok(fs.existsSync(path.join(root, f)) || f.startsWith("out/"), `${f} exists`);
    assert.ok(shipped(f), `${f} is listed in .vscodeignore`);
  }
});

test("sharing is off by default, user-level only, and hidden from every menu until allowed", () => {
  const c = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")).contributes;
  const setting = c.configuration.properties["quickdbd.allowSharing"];
  assert.equal(setting.default, false);
  assert.equal(setting.scope, "application", "a workspace's settings.json can't turn it on");
  const entries = Object.values(c.menus as Record<string, { command: string; when?: string }[]>)
    .flat()
    .filter((m) => m.command === "quickdbd.share");
  assert.ok(entries.length >= 2, "the Command Palette and the schema row menu");
  for (const m of entries) assert.match(m.when ?? "", /^config\.quickdbd\.allowSharing && /);
});

test("Cmd/Ctrl+K V opens the diagram in every schema language, like the editor title button", () => {
  const c = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")).contributes;
  const key = c.keybindings.find((k: { command: string }) => k.command === "quickdbd.openPreview");
  const title = c.menus["editor/title"].find((m: { command: string }) => m.command === "quickdbd.openPreview");
  assert.equal(key.when, title.when);
});

test("a schema row offers only the conversion to the other syntax", () => {
  const c = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")).contributes;
  const rows = c.menus["view/item/context"] as { command: string; when: string }[];
  // `viewItem =~ /re/` in a when clause, tested against the contextValue sidebar.ts gives a schema row.
  const shows = (command: string, item: string) =>
    rows.some((m) => {
      if (m.command !== command) return false;
      const re = /viewItem =~ \/(.+)\/$/.exec(m.when)?.[1];
      return re ? new RegExp(re).test(item) : m.when.endsWith(`viewItem == ${item}`);
    });
  assert.deepEqual(
    ["schema.quickdbd", "schema.dbml", "schema"].map((item) => [shows("quickdbd.convertToDbml", item), shows("quickdbd.convertToQuickdbd", item)]),
    [[true, false], [false, true], [true, true]],
  );
  for (const item of ["schema.quickdbd", "schema.dbml", "schema"]) assert.ok(shows("quickdbd.openPreview", item), item);
});
