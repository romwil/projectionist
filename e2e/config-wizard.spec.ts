import { expect, test } from "@playwright/test";
import { mockCuratorApis, mockServiceFailure, resetMockCertifications, setForceWizardIncomplete } from "./fixtures/api-mocks";
import { resetOnboarding } from "./fixtures/helpers";
import { certifyInfrastructureStep } from "./fixtures/selectors";

async function goToInfrastructureStep(page: import("@playwright/test").Page) {
  await page.getByTestId("wizard-step-infrastructure").click();
  await expect(page.getByRole("heading", { name: /Connect your stack/ })).toBeVisible();
}

test.describe("Config onboarding wizard", () => {
  test.beforeEach(async ({ page, request }) => {
    resetMockCertifications();
    setForceWizardIncomplete(true);
    await resetOnboarding(request, false);
    await mockCuratorApis(page);
    await page.goto("/config");
    await page.getByTestId("wizard-nav").waitFor();
  });

  test("loads three-step wizard navigation", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "First-run setup" })).toBeVisible();
    await expect(page.getByTestId("wizard-step-identity_seed")).toBeVisible();
    await expect(page.getByTestId("wizard-step-infrastructure")).toBeVisible();
    await expect(page.getByTestId("wizard-step-dropdown_mapping")).toBeVisible();
  });

  test("gates mapping step until Plex is certified", async ({ page }) => {
    await goToInfrastructureStep(page);
    await expect(page.getByTestId("wizard-step-dropdown_mapping")).toBeDisabled();
    await expect(page.getByTestId("wizard-next")).toBeDisabled();
  });

  test("shows infrastructure verification step", async ({ page }) => {
    await goToInfrastructureStep(page);
    await expect(page.getByTestId("verify-llm")).toBeVisible();
  });

  test("certifies infrastructure services with mocked verify endpoints", async ({ page }) => {
    await goToInfrastructureStep(page);
    await certifyInfrastructureStep(page);
  });

  test("shows Plex library dropdowns on mapping step", async ({ page }) => {
    await goToInfrastructureStep(page);
    await certifyInfrastructureStep(page);

    await page.getByTestId("wizard-next").click();
    await expect(page.getByRole("heading", { name: /Choose your libraries/ })).toBeVisible();

    await expect(page.getByTestId("plex-movie-section")).toBeEnabled({ timeout: 10_000 });
    await expect(page.getByTestId("plex-tv-section")).toBeEnabled();

    await page.getByTestId("plex-movie-section").selectOption("1");
    await page.getByTestId("plex-tv-section").selectOption("2");
  });

  test("shows inline error alert when service verify fails", async ({ page }) => {
    await mockServiceFailure(page, "llm", "Invalid API key");
    await goToInfrastructureStep(page);

    await page.getByTestId("verify-llm").click();
    await expect(page.getByTestId("inline-alert-error")).toContainText("Invalid API key", {
      timeout: 10_000,
    });
  });

  test("secret show/hide toggle works in wizard", async ({ page }) => {
    await goToInfrastructureStep(page);

    const toggle = page.getByTestId("secret-toggle-llm_api_key");
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
    await toggle.click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible();
  });
});
