/* Compare with Git Ref: the diagram coloured by what changed since a branch, tag or commit, and kept up to date as you
 * edit (`qdbd serve --diff-base`, shown by preview.ts). */
import { execFile } from "node:child_process";
import * as vscode from "vscode";

const MAX_REFS = 50;

/** A ref picked from the repository's branches and tags, most recent first, or typed in. */
export async function pickRef(cwd: string): Promise<string | undefined> {
  const other = "Other…";
  const items: vscode.QuickPickItem[] = [
    { label: "HEAD", description: "the last commit: shows what you haven't committed" },
    ...(await gitRefs(cwd)).map((label) => ({ label })),
    { label: other, description: "a commit, or anything else git understands" },
  ];
  const pick = await vscode.window.showQuickPick(items, { title: "Compare with", placeHolder: "A branch, tag or commit" });
  if (pick?.label !== other) return pick?.label;
  const typed = await vscode.window.showInputBox({ title: "Compare with", prompt: "A branch, tag or commit", placeHolder: "origin/main" });
  return typed?.trim() || undefined;
}

function gitRefs(cwd: string): Promise<string[]> {
  const args = ["for-each-ref", "--sort=-committerdate", `--count=${MAX_REFS}`, "--format=%(refname)"];
  return new Promise((resolve) => {
    execFile("git", [...args, "refs/heads", "refs/remotes", "refs/tags"], { cwd, timeout: 10000 }, (err, stdout) => {
      if (err) return resolve([]); // not a repository, or no git: HEAD and Other… are still offered
      const refs = stdout.split("\n").filter((r) => r && !r.endsWith("/HEAD"));
      resolve(refs.map((r) => r.replace(/^refs\/(heads|remotes|tags)\//, "")));
    });
  });
}
