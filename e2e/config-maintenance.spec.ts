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
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
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

  test("secret show/hide works for typed drafts and stored reveals", async ({ page }) => {
    await page.goto("/admin/connections");
    const secretInput = page.getByTestId("secret-input-llm_api_key");
    const toggle = page.getByTestId("secret-toggle-llm_api_key");

    await expect(secretInput).toBeVisible();
    await expect(secretInput).toHaveAttribute("type", "password");

    // When no draft and key is unset, Show stays hidden.
    // If a prior run left llm_api_key_set, Show may already be present — either path is fine.
    const initiallyVisible = await toggle.count();
    if (initiallyVisible === 0) {
      await secretInput.fill("sk-draft-for-reveal");
      await expect(toggle).toBeVisible();
      await toggle.click();
      await expect(secretInput).toHaveAttribute("type", "text");
      await expect(secretInput).toHaveValue("sk-draft-for-reveal");
      await toggle.click();
      await expect(secretInput).toHaveAttribute("type", "password");
      return;
    }

    // Configured (empty) field: Show fetches via /api/settings/secrets/reveal.
    await page.route("**/api/settings/secrets/reveal", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ field: "llm_api_key", value: "sk-stored-reveal" }),
      });
    });
    await toggle.click();
    await expect(secretInput).toHaveAttribute("type", "text");
    await expect(secretInput).toHaveValue("sk-stored-reveal");
    await toggle.click();
    await expect(secretInput).toHaveAttribute("type", "password");
  });

  test("persona and libraries live on their admin routes", async ({ page }) => {
    await page.goto("/admin/persona");
    await expect(page.getByTestId("persona-section")).toBeVisible();
    await expect(page.getByTestId("persona-preset-grid")).toBeVisible();

    await page.goto("/admin/libraries");
    await expect(page.getByTestId("plex-library-mapping")).toBeVisible();

    await page.goto("/admin/advanced");
    await expect(page.getByTestId("advanced-settings")).toBeVisible();
    await expect(page.getByTestId("advanced-mcp")).toBeVisible();
  });

  test("library sync card is on sync route", async ({ page }) => {
    await page.goto("/admin/sync");
    await expect(page.getByTestId("library-sync-card")).toBeVisible();
    await expect(page.getByTestId("library-sync-button")).toBeVisible();
    await expect(page.getByTestId("library-sync-card")).toContainText("Library sync");
    await expect(page.locator("body")).not.toContainText("(Phase 8)");
  });
});
