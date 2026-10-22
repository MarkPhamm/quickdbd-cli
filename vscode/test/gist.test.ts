import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { cacheFile, gistFilename, publish, shareKey, type Api, type ApiResult } from "../src/gist.ts";
import { targetTitle } from "../src/target.ts";

/** A fake GitHub: records calls; `patch` is the status PATCH answers with. */
function github(patch = 200): { api: Api; calls: string[] } {
  const calls: string[] = [];
  const api: Api = async (method, endpoint, body) => {
    const files = Object.keys((body as { files: object }).files);
    calls.push(`${method} ${endpoint} ${files.join(",")}`);
    const gist: ApiResult["json"] = { id: "abc123", html_url: "https://gist.github.com/abc123", owner: { login: "me" } };
    if (method === "PATCH") return { status: patch, json: patch === 200 ? gist : { message: "Not Found" } };
    return { status: 201, json: { ...gist, id: "new456" } };
  };
  return { api, calls };
}

function tmp(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "qdbd-gist-"));
}

test("titles, file names and cache location follow qdbd share", () => {
  assert.equal(targetTitle({ cwd: "/w/erd", paths: ["."] }), "erd");
  assert.equal(targetTitle({ cwd: "/w", paths: ["shop.txt"] }), "shop");
  assert.equal(gistFilename("my shop (v2)"), "my-shop-v2.html");
  assert.equal(gistFilename("..."), "diagram.html");
  assert.equal(cacheFile({ QDBD_CACHE_DIR: "/c" }, "/h"), path.join("/c", "shares.json"));
  assert.equal(cacheFile({ XDG_CACHE_HOME: "/x" }, "/h"), path.join("/x", "qdbd", "shares.json"));
  assert.equal(cacheFile({}, "/h"), path.join("/h", ".cache", "qdbd", "shares.json"));
});

test("the share key is share.share_key: resolved paths plus '#'", () => {
  const dir = fs.realpathSync(tmp());
  fs.writeFileSync(path.join(dir, "b.txt"), "");
  fs.writeFileSync(path.join(dir, "a.txt"), "");
  assert.equal(shareKey({ cwd: dir, paths: ["b.txt", "a.txt"] }), `${dir}${path.sep}a.txt|${dir}${path.sep}b.txt#`);
  assert.equal(shareKey({ cwd: dir, paths: ["."] }), `${dir}#`);
});

test("first share makes a secret gist and remembers it; the next one updates it", async () => {
  const file = path.join(tmp(), "shares.json");
  const { api, calls } = github();
  const first = await publish(api, "<html>", "shop", "K#", file);
  assert.deepEqual(calls, ["POST /gists shop.html"]);
  assert.equal(first.link, "https://gistpreview.github.io/?new456");
  assert.equal(first.altLink, "https://gist.githack.com/me/new456/raw/shop.html");
  assert.ok(!first.updated);
  assert.deepEqual(JSON.parse(fs.readFileSync(file, "utf8")), { "K#": { file: "shop.html", id: "new456", owner: "me" } });

  const second = await publish(api, "<html>", "shop", "K#", file);
  assert.equal(calls[1], "PATCH /gists/new456 shop.html");
  assert.ok(second.updated);
});

test("reads gists the CLI remembered, and replaces one that's gone", async () => {
  const file = path.join(tmp(), "shares.json");
  fs.writeFileSync(file, JSON.stringify({ "K#": { id: "old1", owner: "me", file: "erd.html" } }));
  const { api, calls } = github(404);
  const r = await publish(api, "<html>", "shop", "K#", file);
  assert.deepEqual(calls, ["PATCH /gists/old1 erd.html", "POST /gists shop.html"]);
  assert.equal(r.link, "https://gistpreview.github.io/?new456");
  assert.equal(JSON.parse(fs.readFileSync(file, "utf8"))["K#"].id, "new456");
});

test("other API errors are reported, and nothing is remembered", async () => {
  const file = path.join(tmp(), "shares.json");
  const api: Api = async () => ({ status: 401, json: { message: "Bad credentials" } });
  await assert.rejects(publish(api, "<html>", "shop", "K#", file), /GitHub gist creation failed \(401\): Bad credentials/);
  assert.ok(!fs.existsSync(file));
});
