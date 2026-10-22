// Runs test/integration/suite.ts inside a real VS Code, on a scratch git repository holding a copy of examples/ (a
// standalone sample next to synthetic/, a separate multi-file project) and a dbt project (jaffle/target/).
// qdbd comes from QDBD_PATH, else the repo's .venv. QDBD_TEST_INSTALL=1 also tests installing qdbd from this checkout.
import { runTests } from "@vscode/test-electron";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const ext = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const repo = path.resolve(ext, "..");
const ws = fs.mkdtempSync(path.join(os.tmpdir(), "qdbd-vscode-"));
// One level down, so the .vscode settings folder isn't inside examples/ (it would change how folders are judged).
fs.cpSync(path.join(repo, "examples"), path.join(ws, "examples"), { recursive: true });
fs.cpSync(path.join(repo, "tests", "fixtures", "jaffle"), path.join(ws, "jaffle", "target"), { recursive: true });
const bin = process.platform === "win32" ? path.join("Scripts", "qdbd.exe") : path.join("bin", "qdbd");
const qdbd = process.env.QDBD_PATH || path.join(repo, ".venv", bin);
fs.mkdirSync(path.join(ws, ".vscode"));
fs.writeFileSync(path.join(ws, ".vscode", "settings.json"), JSON.stringify({ "quickdbd.qdbdPath": qdbd }));
for (const args of [["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "base"]]) {
  execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", ...args], { cwd: ws });
}

// Set when this runs from a VS Code terminal or extension; it would start the downloaded VS Code as plain Node.
delete process.env.ELECTRON_RUN_AS_NODE;

try {
  await runTests({
    extensionDevelopmentPath: ext,
    extensionTestsPath: path.join(ext, "out", "test", "suite.js"),
    // QDBD_CDP=port: open a DevTools port, to look inside the preview webview while QDBD_HOLD keeps it open.
    launchArgs: [
      ws,
      "--disable-extensions",
      "--disable-workspace-trust",
      ...(process.env.QDBD_CDP ? [`--remote-debugging-port=${process.env.QDBD_CDP}`] : []),
    ],
    extensionTestsEnv: {
      QDBD_HOLD: process.env.QDBD_HOLD ?? "",
      QDBD_TEST_INSTALL: process.env.QDBD_TEST_INSTALL ?? "",
      ...(process.env.QDBD_TEST_INSTALL ? { QDBD_PIP_SPEC: repo } : {}),
    },
  });
} finally {
  fs.rmSync(ws, { recursive: true, force: true });
}
