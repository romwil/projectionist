import { expect, test } from "@playwright/test";
import {
  mockCuratorApis,
  mockSetupStatus,
  resetMockCertifications,
  setForceWizardIncomplete,
} from "./fixtures/api-mocks";

test.describe("Setup incomplete banner", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    setForceWizardIncomplete(true);
    await mockCuratorApis(page);
    // Mock status so this suite stays isolated when a shared e2e server already
    // completed onboarding (API refuses to unset onboarding_complete).
    await mockSetupStatus(page, { onboardingComplete: false });
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
  });

  test("shows setup banner when onboarding is incomplete", async ({ page }) => {
    await expect(page.getByTestId("setup-banner")).toBeVisible();
    await expect(page.getByTestId("setup-banner")).toContainText("Finish setup");
  });

  test("banner links to admin page", async ({ page }) => {
    await page.getByTestId("setup-banner").getByRole("link", { name: "Admin" }).click();
    await expect(page).toHaveURL(/\/admin/);
    await expect(page.getByRole("heading", { name: "First-run setup" })).toBeVisible();
  });
});
