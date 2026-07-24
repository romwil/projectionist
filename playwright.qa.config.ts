/**
 * Playwright config for the multi-role QA sidecar (auth ON).
 * Does not start a temp e2e server — point at a running stack.
 *
 * Save storageState + smoke:
 *   set -a && source .env.qa && set +a
 *   CURATORX_E2E_QA_ROLES=1 npx playwright test --config=playwright.qa.config.ts
 *
 * Past-login suites: point a test at `storageState: 'e2e/.auth/owner.json'` (etc.)
 * or add a project that uses one of those files — see docs/TESTING.md.
 */

import { defineConfig, devices } from "@playwright/test";

const baseURL = (
  process.env.QA_BASE_URL ||
  process.env.E2E_BASE_URL ||
  "http://10.10.1.202:8790"
).replace(/\/$/, "");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 60_000,
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  // No webServer — QA container must already be up on baseURL.
  projects: [
    {
      name: "qa-setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "qa-roles",
      testMatch: /live-roles\.spec\.ts/,
      dependencies: process.env.QA_SKIP_SETUP === "1" ? [] : ["qa-setup"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
