/* The QuickDBD sidebar: every schema in the workspace (tables and columns, from `qdbd check --symbols`) and the
 * extension's actions, one click each. Schemas are found with the same test as opening a file as QuickDBD
 * (target.ts) and checked from disk; one with an editor open keeps the editor's checks (checker.ts). */
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { isSchemaLanguage, type Checker } from "./checker.ts";
import type { Found, Qdbd, Source } from "./cli.ts";
import { columnDetail, tablesByFile, targetKey, type Column, type Table, type Target } from "./schema.ts";
import { findTarget, isSchemaFile, targetTitle } from "./target.ts";

// Never schemas: hidden folders (.git, .venv, editor history and test sandboxes such as .vscode-test, like
// target.ts's folder walk), dependencies and build output.
const SKIP = ["node_modules", "venv", "dbt_packages", "target", "site", "dist", "build"];
const EXCLUDE = `**/{.*,${SKIP.join(",")}}/**`;
const MAX_FILES = 5000;
const MAX_BYTES = 2_000_000;
const RESCAN_DELAY = 500;

/** A schema: what qdbd runs on, and one of its files (absolute), to open it by. */
export interface Schema {
  target: Target;
  file: string;
}

export type Node =
  | ({ kind: "schema" } & Schema)
  | ({ kind: "file"; tables: Table[] } & Schema)
  | ({ kind: "table"; table: Table } & Schema)
  | ({ kind: "column"; table: Table; column: Column } & Schema);

export function isSchemaArg(v: unknown): v is Schema {
  return !!v && typeof v === "object" && "target" in v && "file" in v && typeof v.file === "string";
}

const plural = (n: number, what: string) => `${n} ${what}${n === 1 ? "" : "s"}`;

export class Schemas implements vscode.TreeDataProvider<Node>, vscode.Disposable {
  private schemas = new Map<string, Schema>();
  private scanned: Promise<void> | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private readonly changed = new vscode.EventEmitter<Node | undefined>();
  readonly onDidChangeTreeData = this.changed.event;
  private readonly subs: vscode.Disposable[] = [];

  private readonly checker: Checker;
  private readonly qdbd: Qdbd;

  constructor(checker: Checker, qdbd: Qdbd) {
    this.checker = checker;
    this.qdbd = qdbd;
    const watcher = vscode.workspace.createFileSystemWatcher("**/{*.txt,*.dbml,*.layout.json}");
    this.subs.push(
      watcher,
      watcher.onDidCreate((uri) => skipped(uri) || this.rescanSoon()),
      watcher.onDidDelete((uri) => skipped(uri) || this.rescanSoon()),
      watcher.onDidChange((uri) => skipped(uri) || this.changedOnDisk(uri)),
      checker.onDidUpdate(() => this.changed.fire(undefined)),
      qdbd.onDidInstall(() => this.refresh()),
      this.changed,
    );
  }

  /** Look for schemas again (the refresh button, a file created or deleted). */
  refresh(): void {
    this.scanned = undefined;
    this.changed.fire(undefined);
  }

  private rescanSoon(): void {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.refresh(), RESCAN_DELAY);
  }

  /** A schema file edited outside VS Code (a git pull, `qdbd import`): check it again, unless an editor already does. */
  private changedOnDisk(uri: vscode.Uri): void {
    if (!/\.(txt|dbml)$/i.test(uri.fsPath)) return; // a layout file: positions only
    if (vscode.workspace.textDocuments.some((d) => d.uri.fsPath === uri.fsPath)) return;
    const s = this.schemas.get(targetKey(findTarget(uri.fsPath, vscode.workspace.getWorkspaceFolder(uri)?.uri.fsPath)));
    if (s) void this.checker.checkTarget(s.target);
  }

  /** Every schema in the workspace, by title. Waits for the scan; checks keep arriving after it. */
  async all(): Promise<Schema[]> {
    if (!(await this.qdbd.exe())) return [];
    this.scanned ??= this.scan();
    await this.scanned;
    return [...this.schemas.values()].sort((a, b) => targetTitle(a.target).localeCompare(targetTitle(b.target)));
  }

  schemaOf(doc: vscode.TextDocument): Schema {
    return { target: this.checker.targetFor(doc), file: doc.uri.fsPath };
  }

  private async scan(): Promise<void> {
    const auto = vscode.workspace.getConfiguration("quickdbd").get<boolean>("autoDetect", true);
    const found = new Map<string, Schema>();
    for (const uri of await vscode.workspace.findFiles("**/*.{txt,dbml}", EXCLUDE, MAX_FILES)) {
      const file = uri.fsPath;
      let text: string;
      try {
        if (fs.statSync(file).size > MAX_BYTES) continue;
        text = fs.readFileSync(file, "utf8");
      } catch {
        continue;
      }
      if (!isSchemaFile(file, text, auto)) continue;
      const target = findTarget(file, vscode.workspace.getWorkspaceFolder(uri)?.uri.fsPath);
      if (!found.has(targetKey(target))) found.set(targetKey(target), { target, file });
    }
    this.schemas = found;
    void vscode.commands.executeCommand("setContext", "quickdbd.noSchemas", found.size === 0);
    // In the background: each report redraws the tree as it lands (checker.onDidUpdate).
    void (async () => {
      for (const s of found.values()) if (!this.checker.reportOf(s.target)) await this.checker.checkTarget(s.target);
    })();
  }

  async getChildren(n?: Node): Promise<Node[]> {
    if (!n) return (await this.all()).map((s) => ({ kind: "schema", ...s }));
    const report = this.checker.reportOf(n.target);
    if (!report) return [];
    const at = (file: string) => path.resolve(n.target.cwd, file);
    const tables = (ts: Table[]): Node[] => ts.map((table) => ({ kind: "table", table, target: n.target, file: at(table.file) }));
    if (n.kind === "schema") {
      const groups = tablesByFile(report);
      if (groups.length === 1) return tables(groups[0].tables);
      return groups.map((g) => ({ kind: "file", tables: g.tables, target: n.target, file: at(g.file) }));
    }
    if (n.kind === "file") return tables(n.tables);
    if (n.kind === "table") return n.table.columns.map((column) => ({ ...n, kind: "column", column }));
    return [];
  }

  getTreeItem(n: Node): vscode.TreeItem {
    const key = targetKey(n.target);
    const Collapsed = vscode.TreeItemCollapsibleState.Collapsed;
    if (n.kind === "schema") {
      const report = this.checker.reportOf(n.target);
      const item = new vscode.TreeItem(targetTitle(n.target), Collapsed);
      item.id = `s:${key}`;
      item.contextValue = "schema";
      const errors = report?.errors ?? 0;
      const files = report ? new Set((report.tables ?? []).map((t) => t.file)).size : 0;
      item.description = !report
        ? "checking…"
        : [plural(report.tables?.length ?? 0, "table"), files > 1 && plural(files, "file"), errors && plural(errors, "error")]
            .filter(Boolean)
            .join(" · ");
      item.iconPath = errors
        ? new vscode.ThemeIcon("error", new vscode.ThemeColor("list.errorForeground"))
        : new vscode.ThemeIcon("database");
      item.tooltip = path.join(n.target.cwd, n.target.paths[0] === "." ? "" : n.target.paths[0]);
      item.accessibilityInformation = { label: `${item.label}, ${item.description}` }; // not the tooltip's path
      return item;
    }
    if (n.kind === "file") {
      const item = new vscode.TreeItem(path.relative(n.target.cwd, n.file), Collapsed);
      item.id = `f:${key}:${n.file}`;
      item.resourceUri = vscode.Uri.file(n.file);
      item.iconPath = vscode.ThemeIcon.File;
      item.description = plural(n.tables.length, "table");
      return item;
    }
    if (n.kind === "table") {
      const t = n.table;
      const item = new vscode.TreeItem(t.name, t.columns.length ? Collapsed : vscode.TreeItemCollapsibleState.None);
      item.id = `t:${key}:${t.name}`;
      item.contextValue = "table";
      item.iconPath = new vscode.ThemeIcon("table");
      item.description = t.aliases.length ? `as ${t.aliases.join(", ")}` : undefined;
      const where = `${path.relative(n.target.cwd, n.file)}:${t.line}`;
      item.tooltip = new vscode.MarkdownString().appendMarkdown(`**${t.name}**\n\n`);
      if (t.doc) item.tooltip.appendText(t.doc + "\n\n");
      item.tooltip.appendMarkdown(`${plural(t.columns.length, "column")} · \`${where}\``);
      item.command = openAt(n.file, t.line);
      return item;
    }
    const c = n.column;
    const item = new vscode.TreeItem(c.name, vscode.TreeItemCollapsibleState.None);
    item.id = `c:${key}:${n.table.name}:${c.name}`;
    item.description = columnDetail(c);
    item.iconPath = new vscode.ThemeIcon(c.pk ? "key" : c.fk ? "link" : "symbol-field");
    item.command = openAt(n.file, c.line);
    return item;
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.subs.forEach((s) => s.dispose());
  }
}

/** In a folder the scan skips (EXCLUDE), so file events there don't trigger a rescan. */
function skipped(uri: vscode.Uri): boolean {
  const root = vscode.workspace.getWorkspaceFolder(uri)?.uri.fsPath;
  const dirs = path.relative(root ?? path.parse(uri.fsPath).root, uri.fsPath).split(path.sep).slice(0, -1);
  return dirs.some((d) => d.startsWith(".") || SKIP.includes(d));
}

function openAt(file: string, line: number): vscode.Command {
  const at = new vscode.Range(line - 1, 0, line - 1, 0);
  return { command: "vscode.open", title: "Open", arguments: [vscode.Uri.file(file), { selection: at }] };
}

const SOURCES: Record<Source, string> = {
  setting: "from quickdbd.qdbdPath",
  workspace: "the workspace's virtualenv",
  extension: "installed by the extension",
  path: "on PATH",
};

/** The Actions view: each command, run on the current schema (see `Sidebar.current`), and the qdbd in use. */
class Actions implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly changed = new vscode.EventEmitter<undefined>();
  readonly onDidChangeTreeData = this.changed.event;
  private cli: Found | undefined | null = null; // null: not looked up yet
  private readonly sub: vscode.Disposable;

  private readonly qdbd: Qdbd;

  constructor(qdbd: Qdbd) {
    this.qdbd = qdbd;
    this.sub = qdbd.onDidResolve((f) => {
      this.cli = f;
      this.changed.fire(undefined);
    });
  }

  async getChildren(): Promise<vscode.TreeItem[]> {
    if (this.cli === null) this.cli = await this.qdbd.found();
    const row = (label: string, icon: string, command: string, tooltip?: string) => {
      const item = new vscode.TreeItem(label);
      item.iconPath = new vscode.ThemeIcon(icon);
      item.command = { command, title: label };
      item.tooltip = tooltip;
      item.accessibilityInformation = { label }; // a string tooltip would be read instead
      return item;
    };
    const cli = this.cli
      ? row(`qdbd ${this.cli.version.join(".")}`, "check", "quickdbd.installCli", `${this.cli.exe}\nClick to install or update the extension's own copy.`)
      : row("Install qdbd", "warning", "quickdbd.installCli", "The extension runs the qdbd CLI. This installs it (about a minute).");
    if (this.cli) {
      cli.description = SOURCES[this.cli.source];
      cli.accessibilityInformation = { label: `${cli.label}, ${cli.description}` };
    }
    return [
      row("Open Diagram", "open-preview", "quickdbd.openPreview"),
      row("Compare with Git Ref…", "git-compare", "quickdbd.compare", "The diagram coloured by what changed since a branch, tag or commit"),
      row("Export…", "desktop-download", "quickdbd.export", "PNG, SVG, draw.io or an HTML page"),
      row("Share as a Gist Link", "link-external", "quickdbd.share", "A secret gist; the link is copied"),
      row("Convert to DBML", "arrow-swap", "quickdbd.convertToDbml", "The schema in dbdiagram.io's syntax; what DBML can't express is listed"),
      row("Convert to QuickDBD Syntax", "arrow-swap", "quickdbd.convertToQuickdbd", "The schema in QuickDBD's syntax; what QuickDBD can't express is listed"),
      row("Import dbt Project…", "database", "quickdbd.importDbt", "Schema files from target/manifest.json"),
      row("New Schema File…", "new-file", "quickdbd.newSchema"),
      cli,
    ];
  }

  getTreeItem(item: vscode.TreeItem): vscode.TreeItem {
    return item;
  }

  dispose(): void {
    this.sub.dispose();
    this.changed.dispose();
  }
}

/** Both views, and the schema the actions run on. */
export class Sidebar implements vscode.Disposable {
  readonly schemas: Schemas;
  private readonly schemaView: vscode.TreeView<Node>;
  private readonly actionsView: vscode.TreeView<vscode.TreeItem>;
  private readonly subs: vscode.Disposable[] = [];

  constructor(checker: Checker, qdbd: Qdbd) {
    this.schemas = new Schemas(checker, qdbd);
    const actions = new Actions(qdbd);
    this.schemaView = vscode.window.createTreeView("quickdbd.schemas", { treeDataProvider: this.schemas, showCollapseAll: true });
    this.actionsView = vscode.window.createTreeView("quickdbd.actions", { treeDataProvider: actions });
    const label = () =>
      void this.current().then((s) => (this.actionsView.description = s ? targetTitle(s.target) : undefined));
    this.subs.push(
      this.schemas,
      actions,
      this.schemaView,
      this.actionsView,
      this.schemaView.onDidChangeSelection(label),
      this.schemas.onDidChangeTreeData(label),
      vscode.window.onDidChangeActiveTextEditor(label),
    );
  }

  /** The active QuickDBD editor's schema, else the one selected in Schemas, else the workspace's only one. That
   * last needs a scan, which only runs with the sidebar open, or with `scan` (a command looking for a schema). */
  async current(scan = false): Promise<Schema | undefined> {
    const doc = vscode.window.activeTextEditor?.document;
    if (doc && isSchemaLanguage(doc.languageId) && doc.uri.scheme === "file") return this.schemas.schemaOf(doc);
    const picked = this.schemaView.selection[0];
    if (picked) return { target: picked.target, file: picked.file };
    if (!scan && !this.schemaView.visible && !this.actionsView.visible) return undefined;
    const all = await this.schemas.all();
    return all.length === 1 ? all[0] : undefined;
  }

  dispose(): void {
    this.subs.forEach((s) => s.dispose());
  }
}
