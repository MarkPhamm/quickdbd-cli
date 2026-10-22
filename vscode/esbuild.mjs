// Bundles the extension (and, for development, the integration test suite) into out/.
import * as esbuild from "esbuild";

const production = process.argv.includes("--production");
const watch = process.argv.includes("--watch");
const common = {
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node20",
  external: ["vscode"],
  sourcemap: !production,
  minify: production,
  logLevel: "info",
};
const builds = [{ ...common, entryPoints: ["src/extension.ts"], outfile: "out/extension.js" }];
if (!production) builds.push({ ...common, entryPoints: ["test/integration/suite.ts"], outfile: "out/test/suite.js" });

if (watch) {
  for (const b of builds) await (await esbuild.context(b)).watch();
} else {
  await Promise.all(builds.map((b) => esbuild.build(b)));
}
