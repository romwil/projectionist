import { expect, test } from "@playwright/test";

/**
 * Optional hybrid e2e against a real running CuratorX stack (no API mocks).
 *
 * Skipped unless CURATORX_E2E_LIVE=1. Typical usage:
 *
 *   docker compose up -d
 *   CURATORX_E2E_LIVE=1 E2E_MOCK_APIS=0 E2E_BASE_URL=http://127.0.0.1:8788 npm run test:e2e:live-stack
 *
 * Or point E2E_BASE_URL at an existing host. Playwright will not start the
 * temp e2e server when reuseExistingServer is allowed and the URL is up.
 */
const liveEnabled = ["1", "true", "yes"].includes(
  String(process.env.CURATORX_E2E_LIVE || "").trim().toLowerCase(),
);

test.describe("Live stack e2e (opt-in)", () => {
  test.beforeEach(() => {
    test.skip(!liveEnabled, "Set CURATORX_E2E_LIVE=1 to hit a real CuratorX server");
  });

  test("health endpoint is reachable", async ({ request }) => {
    const health = await request.get("/api/health");
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body.status).toBe("ok");
  });

  test("SPA loads without crashing", async ({ page }) => {
    await page.goto("/");
    // Multi-user stacks may redirect to /login; either is a healthy load.
    await expect(page.locator("body")).toBeVisible();
    const login = page.getByTestId("login-page");
    const workspace = page.getByTestId("workspace-main");
    const wizard = page.getByRole("heading", { name: /First-run setup|Settings|Sign in/i });
    await expect(login.or(workspace).or(wizard).first()).toBeVisible({ timeout: 30_000 });
  });
});
