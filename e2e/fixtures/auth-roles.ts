/**
 * Live-stack multi-role auth helpers for the QA sidecar.
 *
 * Guest has two meanings:
 * 1. Public tour — no password, open `/tour` (no storageState needed).
 * 2. Logged-in `role=guest` — optional seeded account for guest shell chrome.
 *
 * Storage files (gitignored): e2e/.auth/{owner,member,youth,guest}.json
 * Generate against the QA stack:
 *   QA_BASE_URL=http://10.10.1.202:8790 npx playwright test e2e/auth.setup.ts
 */

import { expect, type Browser, type FullConfig, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export type QaRole = "owner" | "member" | "youth" | "guest";

const AUTH_DIR = path.join(process.cwd(), "e2e", ".auth");

export function qaBaseURL(): string {
  return (
    process.env.QA_BASE_URL ||
    process.env.E2E_BASE_URL ||
    "http://10.10.1.202:8790"
  ).replace(/\/$/, "");
}

export function storageStatePath(role: QaRole): string {
  return path.join(AUTH_DIR, `${role}.json`);
}

export function credentialsFor(role: QaRole): { username: string; password: string } {
  const map: Record<QaRole, { userEnv: string; passEnv: string; userDefault: string }> = {
    owner: { userEnv: "QA_OWNER_USER", passEnv: "QA_OWNER_PASSWORD", userDefault: "qa-owner" },
    member: { userEnv: "QA_MEMBER_USER", passEnv: "QA_MEMBER_PASSWORD", userDefault: "qa-member" },
    youth: { userEnv: "QA_YOUTH_USER", passEnv: "QA_YOUTH_PASSWORD", userDefault: "qa-youth" },
    guest: { userEnv: "QA_GUEST_USER", passEnv: "QA_GUEST_PASSWORD", userDefault: "qa-guest" },
  };
  const entry = map[role];
  const username = process.env[entry.userEnv] || entry.userDefault;
  const password = process.env[entry.passEnv] || "";
  if (!password || password.startsWith("change-me-")) {
    throw new Error(`Set ${entry.passEnv} (from .env.qa) before saving ${role} storageState`);
  }
  return { username, password };
}

/** UI local login → persist Playwright storageState for later projects. */
export async function loginLocalViaUi(page: Page, role: QaRole): Promise<void> {
  const { username, password } = credentialsFor(role);
  await page.goto("/login");
  await expect(page.getByTestId("login-page")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("local-login-section")).toBeVisible();
  await page.getByTestId("local-username").fill(username);
  await page.getByTestId("local-password").fill(password);
  await page.getByTestId("local-login-submit").click();
  await expect(page.getByTestId("login-page")).toHaveCount(0, { timeout: 30_000 });
}

export async function saveRoleStorageState(browser: Browser, role: QaRole): Promise<string> {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const context = await browser.newContext({ baseURL: qaBaseURL() });
  const page = await context.newPage();
  await loginLocalViaUi(page, role);
  const out = storageStatePath(role);
  await context.storageState({ path: out });
  await context.close();
  return out;
}

/** Empty / cleared state for public guest tour (no session cookie). */
export async function saveGuestTourStorageState(browser: Browser): Promise<string> {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const context = await browser.newContext({ baseURL: qaBaseURL() });
  const page = await context.newPage();
  await page.goto("/tour");
  await expect(page.getByTestId("guest-tour-page")).toBeVisible({ timeout: 30_000 });
  const out = path.join(AUTH_DIR, "guest-tour.json");
  await context.storageState({ path: out });
  await context.close();
  return out;
}

export function rolesEnabled(): boolean {
  return ["1", "true", "yes"].includes(
    String(process.env.CURATORX_E2E_QA_ROLES || "").trim().toLowerCase(),
  );
}

/** Optional hook if a FullConfig-driven globalSetup is preferred later. */
export async function ensureAuthDir(_config?: FullConfig): Promise<void> {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
}
