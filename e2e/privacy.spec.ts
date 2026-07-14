import { expect, test } from "@playwright/test";
import { mockAuthUnauthenticated, mockCuratorApis, mockFeatures, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Public privacy disclosure", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test(" /privacy is reachable without a session", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUnauthenticated(page);
    await page.goto("/privacy");
    await expect(page.getByTestId("privacy-page")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: /Privacy/i })).toBeVisible();
    await expect(page.locator("#household-members")).toBeVisible();
    await expect(page.locator("#server-owners")).toBeVisible();
    await expect(page.locator("#mcp")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Exposure matrices/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /We do not/i })).toBeVisible();
  });

  test("login page links to Privacy & data use", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUnauthenticated(page);
    await page.goto("/login");
    await expect(page.getByTestId("login-page")).toBeVisible();
    const privacyLink = page.getByTestId("privacy-link");
    await expect(privacyLink).toBeVisible();
    await expect(privacyLink).toHaveAttribute("href", "/privacy");
    await privacyLink.click();
    await expect(page).toHaveURL(/\/privacy$/);
    await expect(page.getByTestId("privacy-page")).toBeVisible();
  });
});
