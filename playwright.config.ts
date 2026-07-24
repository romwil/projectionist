import { defineConfig, devices } from "@playwright/test";

// Default to 8799 â€” NOT 8788. Locally, :8788 is often an SSH tunnel to production
// (or Docker). With reuseExistingServer, Playwright would hit that live/old UI
// instead of the local build. Override with E2E_PORT / E2E_BASE_URL when needed
// (e.g. live-stack against docker compose on 8788).
const port = process.env.E2E_PORT || "8799";
const baseURL = process.env.E2E_BASE_URL || `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  testIgnore: [/auth\.setup\.ts/, /live-roles\.spec\.ts/],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  timeout: 60_000,
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "node scripts/start-e2e-server.mjs",
    url: `${baseURL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

