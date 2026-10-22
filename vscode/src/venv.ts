/* A virtualenv of the extension's own for qdbd, so it can be installed without a terminal: made with a Python 3.11+
 * that's already on the machine, else with uv (which downloads a Python if it needs one). No `vscode` import, so
 * `node --test` runs this directly. */
import * as os from "node:os";
import * as path from "node:path";
import { atLeast, parseVersion } from "./schema.ts";

/** What gets installed. QDBD_PIP_SPEC overrides it (a local checkout or wheel), for testing unreleased versions. */
export const PACKAGE = process.env.QDBD_PIP_SPEC || "quickdbd-cli";
const MIN_PYTHON = [3, 11];
const PRINT_VERSION = "import sys; print('%d.%d.%d' % sys.version_info[:3])";

export interface ExecResult {
  code: number | null;
  stdout: string;
  stderr: string;
}
export type Exec = (cmd: string, args: string[]) => Promise<ExecResult>;

/** An executable inside a virtualenv. */
export function venvBin(venv: string, name: string, platform: NodeJS.Platform = process.platform): string {
  return platform === "win32" ? path.join(venv, "Scripts", `${name}.exe`) : path.join(venv, "bin", name);
}

/** Pythons to try, most likely first: PATH, then where Homebrew puts one (VS Code started from the Dock may lack it). */
export function pythons(platform: NodeJS.Platform = process.platform): string[][] {
  if (platform === "win32") return [["py", "-3"], ["python"], ["python3"]];
  const names = ["python3", "python", "python3.15", "python3.14", "python3.13", "python3.12", "python3.11"];
  return [...names, "/opt/homebrew/bin/python3", "/usr/local/bin/python3"].map((p) => [p]);
}

function uvs(platform: NodeJS.Platform, home: string): string[] {
  const exe = platform === "win32" ? "uv.exe" : "uv";
  return ["uv", path.join(home, ".local", "bin", exe), path.join(home, ".cargo", "bin", exe)];
}

/** The commands that create a virtualenv at `venv` (which must not exist yet) with qdbd in it, or undefined when
 * there's neither a Python 3.11+ nor uv. */
export async function installPlan(
  exec: Exec,
  venv: string,
  platform: NodeJS.Platform = process.platform,
  home: string = os.homedir(),
): Promise<string[][] | undefined> {
  const python = venvBin(venv, "python", platform);
  for (const [cmd, ...pre] of pythons(platform)) {
    const r = await exec(cmd, [...pre, "-c", PRINT_VERSION]);
    const v = r.code === 0 ? parseVersion(r.stdout) : undefined;
    if (v && atLeast(v, MIN_PYTHON)) {
      return [
        [cmd, ...pre, "-m", "venv", venv],
        [python, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", PACKAGE],
      ];
    }
  }
  for (const uv of uvs(platform, home)) {
    if ((await exec(uv, ["--version"])).code === 0) {
      return [
        [uv, "venv", "--python", ">=3.11", venv],
        [uv, "pip", "install", "--python", python, "--upgrade", PACKAGE],
      ];
    }
  }
  return undefined;
}
