#!/usr/bin/env node
/**
 * Playback-fixture server for Playwright.
 * Same boundary as scripts/start-e2e-server.mjs: port 8799, not 8788.
 * Generates clips, then serves them from PROJECTIONIST_FIXTURE_MEDIA_DIR.
 * Never talks to Plex and never binds 8788, 8790, or 8792.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = process.env.E2E_PORT || "8799";
const BANNED = new Set(["8788", "8790", "8792"]);
const FIXTURE_DIR =
  process.env.PROJECTIONIST_FIXTURE_MEDIA_DIR ||
  path.join(ROOT, "e2e", ".playback-fixtures");
const DATA_DIR =
  process.env.E2E_DATA_DIR || mkdtempSync(path.join(os.tmpdir(), "projectionist-playback-e2e-"));

if (BANNED.has(String(PORT))) {
  console.error(`Refusing E2E_PORT ${PORT}. Playback fixtures use 8799.`);
  process.exit(1);
}

function resolvePython(root) {
  const candidates = [
    process.env.PROJECTIONIST_PYTHON,
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function npm(args, cwd) {
  const cmd = process.platform === "win32" ? "npm.cmd" : "npm";
  const result = spawnSync(cmd, args, {
    cwd,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const python = resolvePython(ROOT);
const generate = spawnSync(
  python,
  [path.join(ROOT, "scripts", "generate-playback-fixtures.py"), FIXTURE_DIR],
  { cwd: ROOT, stdio: "inherit" },
);
if (generate.status !== 0) process.exit(generate.status ?? 1);

const distDir = path.join(ROOT, "frontend", "dist");
if (!existsSync(distDir)) {
  console.log("Building frontend for playback fixtures...");
  const frontendDir = path.join(ROOT, "frontend");
  npm(["install"], frontendDir);
  npm(["run", "build"], frontendDir);
}

const env = {
  ...process.env,
  DATA_DIR,
  PORT,
  PROJECTIONIST_FIXTURE_MEDIA_DIR: FIXTURE_DIR,
  PROJECTIONIST_SKIP_DOTENV: "1",
  CURATORX_SKIP_DOTENV: "1",
  PYTHONPATH: [ROOT, process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
  PROJECTIONIST_SETUP_STATE: process.env.PROJECTIONIST_SETUP_STATE || "active",
  PROJECTIONIST_THEATER_PORT: process.env.PROJECTIONIST_THEATER_PORT || "8796",
};

console.log(
  `Starting playback fixture server on :${PORT} (DATA_DIR=${DATA_DIR}, fixtures=${FIXTURE_DIR})`,
);

const child = spawn(python, ["-m", "projectionist.web"], {
  cwd: ROOT,
  env,
  stdio: "inherit",
});

child.on("error", (err) => {
  console.error(err);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
