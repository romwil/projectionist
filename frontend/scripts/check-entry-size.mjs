#!/usr/bin/env node
// Fails when the entry script named in dist/index.html grows past the budget
// or statically pulls in Admin, the theater player, or Chat (PERF-005).
import { readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BUDGET_BYTES = 600 * 1024;
const LAZY_ONLY = [/^AdminRoutes-/, /^LibraryPlayer-/, /^TheaterPlayer-/, /^App-/, /^LivePage-/];

const distDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "dist");
const html = readFileSync(path.join(distDir, "index.html"), "utf8");
const match = html.match(/<script[^>]+type="module"[^>]+src="\/?([^"]+\.js)"/);
if (!match) {
  console.error("check-entry-size: no module script in dist/index.html");
  process.exit(1);
}
const entryPath = path.join(distDir, match[1]);
const bytes = statSync(entryPath).size;
const code = readFileSync(entryPath, "utf8");
const staticImports = [...code.matchAll(/(?:^|[;\n}])\s*import\s*(?:[\w$*{}\s,]+from\s*)?["']\.\/([^"']+)["']/g)].map((m) => m[1]);
const preloads = [...html.matchAll(/rel="modulepreload"[^>]+href="\/?assets\/([^"]+)"/g)].map((m) => m[1]);
const leaked = [...staticImports, ...preloads].filter((name) => LAZY_ONLY.some((re) => re.test(name)));

const kb = (n) => `${(n / 1024).toFixed(1)} kB`;
console.log(`entry ${match[1]}: ${kb(bytes)} (budget ${kb(BUDGET_BYTES)})`);
let failed = false;
if (bytes > BUDGET_BYTES) {
  console.error(`check-entry-size: entry is over budget. Move the new import behind React.lazy instead of raising the budget.`);
  failed = true;
}
if (leaked.length) {
  console.error(`check-entry-size: entry statically loads lazy-only chunks: ${leaked.join(", ")}`);
  failed = true;
}
process.exit(failed ? 1 : 0);
