import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";
import { completeOnboardingViaApi } from "./fixtures/helpers";

test.describe("Admin maintenance dashboard", () => {
  test.beforeEach(async ({ page, request }) => {
    resetMockCertifications();
    await completeOnboardingViaApi(request);
    await mockCuratorApis(page);
  });

  test("shows overview when onboarding is complete", async ({ page }) => {
    await page.goto("/admin/overview");
    await page.getByTestId("maintenance-dashboard").waitFor();
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    await expect(page.getByTestId("maintenance-dashboard")).toBeVisible();
    await expect(page.getByTestId("wizard-nav")).toHaveCount(0);
    await expect(page.getByTestId("admin-rail")).toBeVisible();
  });

  test("/config redirects to admin", async ({ page }) => {
    await page.goto("/config");
    await expect(page).toHaveURL(/\/admin(\/overview)?$/);
  });

  test("can re-run onboarding wizard from overview", async ({ page }) => {
    await page.goto("/admin/overview");
    await page.getByTestId("maintenance-dashboard").waitFor();
    await page.getByTestId("rerun-wizard").click();
    await expect(page.getByRole("heading", { name: "First-run setup" })).toBeVisible();
    await expect(page.getByTestId("wizard-nav")).toBeVisible();
  });

  test("shows LLM test controls on connections", async ({ page }) => {
    await page.goto("/admin/connections");
    await expect(page.getByRole("button", { name: "Test connection" })).toBeVisible();
    await expect(page.getByTestId("certified-badge-llm")).toBeVisible();
  });

  test("secret show/hide toggle switches input type", async ({ page }) => {
    await page.goto("/admin/connections");
    const toggle = page.getByTestId("secret-toggle-llm_api_key");
    const secretInput = page.locator('input[type="password"]').first();

    await expect(secretInput).toBeVisible();
    await toggle.click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible();
  });

  test("persona and libraries live on their admin routes", async ({ page }) => {
    await page.goto("/admin/persona");
    await expect(page.getByTestId("persona-section")).toBeVisible();
    await expect(page.getByTestId("persona-preset-grid")).toBeVisible();

    await page.goto("/admin/libraries");
    await expect(page.getByTestId("plex-library-mapping")).toBeVisible();

    await page.goto("/admin/advanced");
    await expect(page.getByTestId("advanced-toggle")).toBeVisible();
  });

  test("library sync card is on sync route", async ({ page }) => {
    await page.goto("/admin/sync");
    await expect(page.getByTestId("library-sync-card")).toBeVisible();
    await expect(page.getByTestId("library-sync-button")).toBeVisible();
    await expect(page.getByTestId("library-sync-card")).toContainText("Library sync");
    await expect(page.locator("body")).not.toContainText("(Phase 8)");
  });
});
