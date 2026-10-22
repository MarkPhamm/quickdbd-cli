/* Sharing as a secret gist through the GitHub API, with the token from VS Code's GitHub sign-in, so neither the gh CLI
 * nor a terminal is needed. It follows `qdbd share` (share.py): the same description, file name and links, and the
 * same remembered gist per schema in ~/.cache/qdbd/shares.json, so the CLI and the extension update one gist and the
 * link stays the same. No `vscode` import, so `node --test` runs this directly. */
import * as fs from "node:fs";
import * as https from "node:https";
import * as os from "node:os";
import * as path from "node:path";
import type { Target } from "./schema.ts";

export interface ApiResult {
  status: number;
  json: { id?: string; html_url?: string; owner?: { login?: string }; message?: string };
}
export type Api = (method: "POST" | "PATCH", endpoint: string, body: unknown) => Promise<ApiResult>;

export interface Shared {
  link: string; // gistpreview: renders the gist's HTML
  altLink: string; // githack: the raw file as text/html
  gistUrl: string;
  updated: boolean;
}

interface Entry {
  id: string;
  owner: string;
  file: string;
}

/** share.share_key: the resolved input paths, sorted, plus the selector (none here). */
export function shareKey(target: Target): string {
  const real = (p: string) => {
    try {
      return fs.realpathSync(p);
    } catch {
      return p;
    }
  };
  return target.paths.map((p) => real(path.resolve(target.cwd, p))).sort().join("|") + "#";
}

export function cacheFile(env: NodeJS.ProcessEnv = process.env, home: string = os.homedir()): string {
  const base = env.QDBD_CACHE_DIR || path.join(env.XDG_CACHE_HOME || path.join(home, ".cache"), "qdbd");
  return path.join(base, "shares.json");
}

export function gistFilename(title: string): string {
  return (title.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "") || "diagram") + ".html";
}

function load(file: string): Record<string, Entry> {
  try {
    const data: unknown = JSON.parse(fs.readFileSync(file, "utf8"));
    return data && typeof data === "object" ? (data as Record<string, Entry>) : {};
  } catch {
    return {};
  }
}

function save(file: string, data: Record<string, Entry>): void {
  const sorted = (o: object) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => (a < b ? -1 : 1)));
  const out = sorted(Object.fromEntries(Object.entries(data).map(([k, v]) => [k, sorted(v)])));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(out, null, 2) + "\n");
}

function failed(what: string, r: ApiResult): Error {
  return new Error(`GitHub ${what} failed (${r.status}): ${r.json.message ?? "no details"}`);
}

/** Update the gist remembered for `key`, or make a new secret one; remembers it for next time. */
export async function publish(api: Api, page: string, title: string, key: string, file = cacheFile()): Promise<Shared> {
  const cache = load(file);
  let entry: Entry | undefined = cache[key];
  const description = `qdbd ERD: ${title}`;
  let gist: ApiResult["json"] | undefined;
  if (entry) {
    const r = await api("PATCH", `/gists/${entry.id}`, { description, files: { [entry.file]: { content: page } } });
    if (r.status === 200) gist = r.json;
    else if (r.status === 404 || r.status === 403) entry = undefined; // deleted, or another account's: make a new one
    else throw failed("update", r);
  }
  const updated = gist !== undefined;
  const fname = entry?.file ?? gistFilename(title);
  if (!gist) {
    const r = await api("POST", "/gists", { description, public: false, files: { [fname]: { content: page } } });
    if (r.status !== 201 || !r.json.id) throw failed("gist creation", r);
    gist = r.json;
  }
  const id = gist.id!;
  const owner = gist.owner?.login ?? "";
  cache[key] = { id, owner, file: fname };
  save(file, cache);
  return {
    link: `https://gistpreview.github.io/?${id}`,
    altLink: `https://gist.githack.com/${owner}/${id}/raw/${fname}`,
    gistUrl: gist.html_url ?? "",
    updated,
  };
}

/** The GitHub REST API over node:https, which VS Code routes through its proxy settings. */
export function githubApi(token: string): Api {
  return (method, endpoint, body) =>
    new Promise((resolve, reject) => {
      const data = JSON.stringify(body);
      const req = https.request(
        {
          host: "api.github.com",
          path: endpoint,
          method,
          headers: {
            Accept: "application/vnd.github+json",
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(data),
            "User-Agent": "qdbd-vscode",
            "X-GitHub-Api-Version": "2022-11-28",
          },
        },
        (res) => {
          let raw = "";
          res.setEncoding("utf8");
          res.on("data", (c: string) => (raw += c));
          res.on("end", () => {
            let json: ApiResult["json"];
            try {
              json = JSON.parse(raw) as ApiResult["json"];
            } catch {
              json = { message: raw.slice(0, 200) };
            }
            resolve({ status: res.statusCode ?? 0, json });
          });
        },
      );
      req.on("error", reject);
      req.end(data);
    });
}
