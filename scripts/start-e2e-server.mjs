#!/usr/bin/env node
/**
 * Cross-platform E2E server launcher (Playwright webServer).
 * Default port 8799 — not 8788 (often SSH tunnel / Docker to production).
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = process.env.E2E_PORT || "8799";
const DATA_DIR =
  process.env.E2E_DATA_DIR ||
  mkdtempSync(path.join(os.tmpdir(), "curatorx-e2e-"));

function resolvePython(root) {
  const candidates = [
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python"),
  ];
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
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

const distDir = path.join(ROOT, "frontend", "dist");
if (!existsSync(distDir)) {
  console.log("Building frontend for E2E...");
  const frontendDir = path.join(ROOT, "frontend");
  npm(["install"], frontendDir);
  npm(["run", "build"], frontendDir);
}

const python = resolvePython(ROOT);
const env = {
  ...process.env,
  DATA_DIR,
  PORT,
  CURATORX_SKIP_DOTENV: "1",
};

console.log(`Starting CuratorX E2E server on :${PORT} (DATA_DIR=${DATA_DIR})`);

const child = spawn(python, ["-m", "curatorx.web"], {
  cwd: ROOT,
  env,
  stdio: "inherit",
});

child.on("error", (err) => {
  console.error(err);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 1);
});