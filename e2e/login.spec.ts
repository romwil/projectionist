import { expect, test } from "@playwright/test";
import {
  mockAuthUnauthenticated,
  mockAuthUser,
  mockCuratorApis,
  mockFeatures,
  mockPlexLogin,
  resetMockCertifications,
} from "./fixtures/api-mocks";

test.describe("Login flow", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test("skips login when multi-user auth is disabled", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: false });
    await page.goto("/");
    await expect(page).toHaveURL(/\/explore$/);
    await expect(page.getByTestId("explore-hub-links")).toBeVisible();
    await expect(page.getByTestId("login-page")).toHaveCount(0);
  });

  test("redirects to login when multi-user is enabled and session is missing", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUnauthenticated(page);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByTestId("login-page")).toBeVisible();
    await expect(page.getByTestId("sign-in-with-plex")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByTestId("login-page")).toContainText("Plex");
    await expect(page.getByTestId("login-page")).not.toContainText("Multi-user");
    await expect(page.getByTestId("plex-token-input")).toHaveCount(0);
    await expect(page.getByTestId("show-token-login")).toHaveText("Advanced");
  });

  test("plex PIN login returns to Explore home", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockPlexLogin(page);

    await page.goto("/login");
    await expect(page.getByTestId("login-page")).toBeVisible();
    await page.getByTestId("sign-in-with-plex").click();
    // The mock links the PIN as soon as it is created. The first check is immediate,
    // so the waiting card may never paint. EXP-013: post-login home is Explore.
    await expect(page).toHaveURL(/\/explore$/);
    await expect(page.getByTestId("explore-hub-links")).toBeVisible();
    await expect(page.getByTestId("login-page")).toHaveCount(0);
  });

  test("advanced token login stays behind Advanced disclosure", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockPlexLogin(page);

    await page.goto("/login");
    await expect(page.getByTestId("login-page")).toBeVisible();
    await expect(page.getByTestId("plex-token-input")).toHaveCount(0);
    await page.getByTestId("show-token-login").click();
    await expect(page.getByTestId("plex-token-input")).toBeVisible();
    await expect(page.getByTestId("login-page")).toContainText("Recovery only");
    await expect(page.getByTestId("show-token-login")).toHaveText("Hide advanced");
    await page.getByTestId("plex-token-input").fill("mock-plex-token");
    await page.getByTestId("submit-plex-login").click();

    await expect(page).toHaveURL(/\/explore$/);
    await expect(page.getByTestId("explore-hub-links")).toBeVisible();
  });

  test("shows user menu when authenticated in multi-user mode", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page);
    await page.goto("/");
    await expect(page).toHaveURL(/\/explore$/);
    await expect(page.getByTestId("user-menu")).toBeVisible();
    await expect(page.getByTestId("user-menu-trigger")).toContainText("Test User");
  });

  test("profile menu items are clickable and navigate", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page);
    await page.goto("/");
    await expect(page).toHaveURL(/\/explore$/);

    await page.getByTestId("user-menu-trigger").click();
    const panel = page.getByTestId("user-menu-panel");
    await expect(panel).toBeVisible();

    // Click must hit the link, not the page under the dropdown.
    await panel.getByRole("link", { name: "About" }).click();
    await expect(page).toHaveURL(/\/about$/);
  });
});
