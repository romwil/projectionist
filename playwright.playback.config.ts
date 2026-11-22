import { defineConfig, devices } from "@playwright/test";

// Playback fixtures use the mocked e2e port, 8799. Never 8788 (often a tunnel
// to production), and never the household QA or smartmap ports.
const port = process.env.E2E_PORT || "8799";
if (port === "8788" || port === "8790" || port === "8792") {
  throw new Error(`Refusing E2E_PORT ${port}. Playback fixtures use 8799.`);
}
const baseURL = process.env.E2E_BASE_URL || `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /playback-fixtures\.spec\.ts/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  timeout: 180_000,
  use: {
    baseURL,
    channel: "chrome",
    viewport: { width: 1280, height: 720 },
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    launchOptions: {
      args: ["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
    },
  },
  projects: [
    {
      name: "chrome",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chrome",
      },
    },
  ],
  webServer: {
    command: "node scripts/start-playback-fixture-e2e.mjs",
    url: `${baseURL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
