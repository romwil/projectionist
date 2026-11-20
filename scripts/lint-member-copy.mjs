#!/usr/bin/env node
/**
 * EXP-005: fail CI when banned system vocabulary appears in member-facing copy.
 *
 * Scans quoted / JSX text in member-facing frontend + server note modules.
 * Admin / owner workbench paths and pure code identifiers are allowlisted.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const FORBIDDEN = [
  { id: "cosine", re: /\bcosine\b/i },
  { id: "Scheduled Tasks", re: /Scheduled Tasks/ },
  { id: "turnstyle view", re: /turnstyle view/i },
  { id: "agent activity", re: /agent activity/i },
  { id: "CuratorX", re: /CuratorX/ },
];

const ALLOW_PREFIXES = [
  "frontend/src/pages/ScheduledTasksPage.tsx",
  "frontend/src/pages/HelpPage.tsx", // owner jump links gated by showOwnerNav
  "frontend/src/pages/admin/",
  "frontend/src/components/admin/",
  "frontend/src/lib/ownerHealth",
  "frontend/src/lib/scheduledTasks",
  "frontend/src/lib/knowledgeCoverage",
  "frontend/src/lib/agentActivityLog",
  "frontend/src/lib/routeTitles",
  "frontend/src/lib/surpriseNeighbors",
  "frontend/src/lib/turnstyleItems",
  "frontend/src/components/OwnerHealthHero",
  "frontend/src/components/OwnerEmptyStateCta",
  "frontend/src/lib/exploreFeeds",
  "docs/",
  "scripts/lint-member-copy.mjs",
];

const SCAN_ROOTS = [
  "frontend/src/pages",
  "frontend/src/components",
  "frontend/src/lib",
  "projectionist/library/feeds.py",
  "projectionist/library/tonight.py",
  "projectionist/youth/apply.py",
  "projectionist/agent/tools/library.py",
];

function toPosix(p) {
  return p.split(path.sep).join("/");
}

function isAllowed(rel) {
  const posix = toPosix(rel);
  if (posix.includes(".test.") || posix.endsWith(".test.mjs")) return true;
  return ALLOW_PREFIXES.some((prefix) => posix === prefix || posix.startsWith(prefix));
}

function walk(abs, out = []) {
  const st = fs.statSync(abs);
  if (st.isFile()) {
    out.push(abs);
    return out;
  }
  for (const name of fs.readdirSync(abs)) {
    if (name === "node_modules" || name === "dist") continue;
    walk(path.join(abs, name), out);
  }
  return out;
}

function collectFiles() {
  const files = [];
  for (const g of SCAN_ROOTS) {
    const abs = path.join(ROOT, g);
    if (!fs.existsSync(abs)) continue;
    walk(abs, files);
  }
  return files.filter((abs) => {
    const rel = toPosix(path.relative(ROOT, abs));
    if (isAllowed(rel)) return false;
    return /\.(tsx?|jsx?|mjs|py)$/.test(rel);
  });
}

/** Extract likely user-facing string literals (quotes + simple JSX text). */
function extractCopySnippets(line) {
  const snippets = [];
  const quoteRe = /(['"`])(?:\\.|(?!\1)[\s\S])*\1/g;
  let m;
  while ((m = quoteRe.exec(line))) {
    snippets.push(m[0].slice(1, -1));
  }
  // JSX text nodes: >Copy here<
  const jsxRe = />([^<>{][^<>]*)</g;
  while ((m = jsxRe.exec(line))) {
    const t = m[1].trim();
    if (t) snippets.push(t);
  }
  return snippets;
}

function main() {
  const hits = [];
  for (const abs of collectFiles()) {
    const rel = toPosix(path.relative(ROOT, abs));
    const text = fs.readFileSync(abs, "utf8");
    const lines = text.split(/\r?\n/);
    lines.forEach((line, i) => {
      if (/^\s*import\b/.test(line) || /^\s*from\b/.test(line)) return;
      if (/^\s*\/\//.test(line) || /^\s*#/.test(line)) return;
      const snippets = extractCopySnippets(line);
      if (!snippets.length) return;
      for (const snippet of snippets) {
        for (const rule of FORBIDDEN) {
          if (rule.re.test(snippet)) {
            hits.push(`${rel}:${i + 1}: ${rule.id} → ${snippet.trim().slice(0, 120)}`);
          }
        }
      }
    });
  }

  if (hits.length) {
    console.error("EXP-005 member-copy lint failed:\n");
    for (const h of hits) console.error(`  ${h}`);
    console.error(
      `\n${hits.length} hit(s). Member/Youth copy must not use: ${FORBIDDEN.map((f) => f.id).join(", ")}.`,
    );
    process.exit(1);
  }
  console.log(`EXP-005 member-copy lint OK (${collectFiles().length} files scanned).`);
}

main();
