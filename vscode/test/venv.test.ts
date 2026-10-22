import assert from "node:assert/strict";
import * as path from "node:path";
import { test } from "node:test";
import { installPlan, PACKAGE, venvBin, type Exec } from "../src/venv.ts";

/** A fake machine: `versions` maps a command to what it prints for its version (missing: not installed). */
function machine(versions: Record<string, string>): { exec: Exec; tried: string[] } {
  const tried: string[] = [];
  const exec: Exec = async (cmd, args) => {
    tried.push([cmd, ...args.filter((a) => a !== "-c" && !a.startsWith("import"))].join(" "));
    const out = versions[[cmd, ...args.filter((a) => a === "-3")].join(" ")];
    return out === undefined ? { code: null, stdout: "", stderr: "ENOENT" } : { code: 0, stdout: out, stderr: "" };
  };
  return { exec, tried };
}

test("venv executables per platform", () => {
  assert.equal(venvBin("/v", "qdbd", "darwin"), path.join("/v", "bin", "qdbd"));
  assert.equal(venvBin("C:\\v", "qdbd", "win32"), path.join("C:\\v", "Scripts", "qdbd.exe"));
});

test("uses the first Python that is 3.11 or later", async () => {
  const { exec, tried } = machine({ python3: "3.9.6\n", "python3.13": "3.13.1\n", uv: "uv 0.12.0" });
  const plan = await installPlan(exec, "/v", "darwin", "/home/me");
  assert.deepEqual(plan, [
    ["python3.13", "-m", "venv", "/v"],
    [path.join("/v", "bin", "python"), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", PACKAGE],
  ]);
  assert.deepEqual(tried.slice(0, 2), ["python3", "python"], "the plain names first");
});

test("the py launcher on Windows", async () => {
  const { exec } = machine({ "py -3": "3.12.4\n" });
  const plan = await installPlan(exec, "C:\\v", "win32", "C:\\Users\\me");
  assert.deepEqual(plan?.[0], ["py", "-3", "-m", "venv", "C:\\v"]);
});

test("falls back to uv, which fetches its own Python", async () => {
  const uv = path.join("/home/me", ".local", "bin", "uv");
  const { exec } = machine({ python3: "3.9.6\n", [uv]: "uv 0.12.0" });
  const plan = await installPlan(exec, "/v", "linux", "/home/me");
  assert.deepEqual(plan, [
    [uv, "venv", "--python", ">=3.11", "/v"],
    [uv, "pip", "install", "--python", path.join("/v", "bin", "python"), "--upgrade", PACKAGE],
  ]);
});

test("nothing usable: no plan", async () => {
  const { exec } = machine({ python3: "3.10.12\n" });
  assert.equal(await installPlan(exec, "/v", "linux", "/home/me"), undefined);
});
