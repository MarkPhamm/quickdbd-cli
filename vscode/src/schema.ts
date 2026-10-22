/* Pure helpers over `qdbd check --format json --symbols` output and schema text. No vscode import, so
 * they run under `node --test`. The Python parser stays the only parser: these only look things up in
 * its report, or make cheap guesses about plain text (is this a QuickDBD file? which word is under the cursor?). */

export interface Diag {
  path: string;
  line: number;
  message: string;
  severity: "error" | "warning";
}

export interface Column {
  name: string;
  line: number;
}

export interface Table {
  name: string;
  aliases: string[];
  file: string;
  line: number;
  endLine: number;
  columns: Column[];
}

export interface Report {
  ok: boolean;
  errors: number;
  warnings: number;
  diagnostics: Diag[];
  tables?: Table[];
}

/** What `qdbd` is run on: `paths` relative to `cwd`, so report paths come back relative to `cwd` too. */
export interface Target {
  cwd: string;
  paths: string[];
}

export function targetKey(t: Target): string {
  return t.cwd + "\0" + t.paths.join("\0");
}

const SEPARATOR = /^-+\s*$/;
const KEYED = /(^|\s)(PK|FK)(\s|$)|^\s*rel\s/i;

/** A header line followed by a `---` separator, i.e. at least one table. */
export function hasTable(text: string): boolean {
  const lines = text.split(/\r?\n/, 5000);
  for (let i = 1; i < lines.length; i++) {
    const prev = lines[i - 1].trim();
    if (SEPARATOR.test(lines[i]) && prev && !prev.startsWith("#")) return true;
  }
  return false;
}

/** Strict enough to switch a plain .txt to QuickDBD: a table plus a PK/FK/rel line. */
export function looksLikeQuickdbd(text: string): boolean {
  if (!hasTable(text)) return false;
  return text.split(/\r?\n/, 5000).some((l) => !l.trimStart().startsWith("#") && KEYED.test(l));
}

/** The table whose lines include `line` (1-based) in `file` (a report path). */
export function tableAt(report: Report, file: string, line: number): Table | undefined {
  return (report.tables ?? []).find((t) => t.file === file && line >= t.line && line <= t.endLine);
}

/** A table by name or alias: exact first, then case-insensitive (QuickDBD's default). */
export function findTable(report: Report, name: string): Table | undefined {
  const tables = report.tables ?? [];
  const lower = name.toLowerCase();
  return (
    tables.find((t) => t.name === name || t.aliases.includes(name)) ??
    tables.find((t) => t.name.toLowerCase() === lower || t.aliases.some((a) => a.toLowerCase() === lower))
  );
}

export function findColumn(table: Table, name: string): Column | undefined {
  const lower = name.toLowerCase();
  return table.columns.find((c) => c.name === name) ?? table.columns.find((c) => c.name.toLowerCase() === lower);
}

const REF = /("[^"]*"|[^\s".#]+)(?:\.("[^"]*"|[^\s".#]+))?/g;

/** The `Table` or `Table.Column` reference under character `ch` of a line, quotes removed. */
export function refAt(text: string, ch: number): { table: string; column?: string } | undefined {
  const hash = commentStart(text);
  if (hash >= 0 && ch >= hash) return undefined;
  for (const m of text.slice(0, hash >= 0 ? hash : undefined).matchAll(REF)) {
    const start = m.index ?? 0;
    if (ch < start || ch > start + m[0].length) continue;
    const unquote = (s: string) => s.replace(/^"|"$/g, "");
    return m[2] === undefined ? { table: unquote(m[1]) } : { table: unquote(m[1]), column: unquote(m[2]) };
  }
  return undefined;
}

function commentStart(text: string): number {
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '"') quoted = !quoted;
    else if (text[i] === "#" && !quoted) return i;
  }
  return -1;
}

/** "qdbd 0.1.16" -> [0, 1, 16] */
export function parseVersion(out: string): number[] | undefined {
  const m = /(\d+)\.(\d+)\.(\d+)/.exec(out);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : undefined;
}

export function atLeast(v: number[], min: number[]): boolean {
  for (let i = 0; i < min.length; i++) {
    if ((v[i] ?? 0) !== min[i]) return (v[i] ?? 0) > min[i];
  }
  return true;
}

/** The first http(s) URL in some CLI output (`qdbd serve`'s "serving … at URL", `qdbd share`'s link). */
export function firstUrl(out: string): string | undefined {
  return /https?:\/\/[^\s)]+/.exec(out)?.[0];
}
