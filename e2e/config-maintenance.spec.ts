import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";
import { completeOnboardingViaApi } from "./fixtures/helpers";

test.describe("Config maintenance dashboard", () => {
  test.beforeEach(async ({ page, request }) => {
    resetMockCertifications();
    await completeOnboardingViaApi(request);
    await mockCuratorApis(page);
    await page.goto("/config");
    await page.getByTestId("maintenance-dashboard").waitFor();
  });

  test("shows maintenance dashboard when onboarding is complete", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByTestId("maintenance-dashboard")).toBeVisible();
    await expect(page.getByTestId("wizard-nav")).toHaveCount(0);
  });

  test("can re-run onboarding wizard from maintenance", async ({ page }) => {
    await page.getByTestId("rerun-wizard").click();
    await expect(page.getByRole("heading", { name: "First-run setup" })).toBeVisible();
    await expect(page.getByTestId("wizard-nav")).toBeVisible();
  });

  test("shows LLM test controls and certified badge area", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Test connection" })).toBeVisible();
    await expect(page.getByTestId("certified-badge-llm")).toBeVisible();
  });

  test("secret show/hide toggle switches input type", async ({ page }) => {
    const toggle = page.getByTestId("secret-toggle-llm_api_key");
    const secretInput = page.locator('input[type="password"]').first();

    await expect(secretInput).toBeVisible();
    await toggle.click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible();
  });

  test("persona section is available under advanced settings", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /Curation lenses/i })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Behavioral tuning" })).toHaveCount(0);
    await expect(page.getByTestId("plex-library-mapping")).toBeVisible();
    await expect(page.getByTestId("persona-section")).toBeVisible();
    await expect(page.getByTestId("persona-preset-grid")).toBeVisible();
    await expect(page.getByTestId("advanced-toggle")).toBeVisible();
  });

  test("library sync card is present without phase numbering", async ({ page }) => {
    await expect(page.getByTestId("library-sync-card")).toBeVisible();
    await expect(page.getByTestId("library-sync-button")).toBeVisible();
    await expect(page.getByTestId("library-sync-card")).toContainText("Library sync");
    await expect(page.locator("body")).not.toContainText("(Phase 8)");
  });
});
