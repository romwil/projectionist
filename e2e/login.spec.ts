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
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("login-page")).toHaveCount(0);
    await expect(page.getByTestId("workspace-main")).toBeVisible();
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

  test("plex PIN login returns to chat workspace", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockPlexLogin(page);

    await page.goto("/login");
    await expect(page.getByTestId("login-page")).toBeVisible();
    await page.getByTestId("sign-in-with-plex").click();
    await expect(page.getByTestId("plex-pin-waiting")).toBeVisible();
    // Post-login home is the chat workspace (`/` redirects to `/chat`).
    await expect(page).toHaveURL(/\/(chat)?$/);
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("workspace-main")).toBeVisible();
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

    await expect(page).toHaveURL(/\/(chat)?$/);
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("workspace-main")).toBeVisible();
  });

  test("shows user menu when authenticated in multi-user mode", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page);
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("user-menu")).toBeVisible();
    await expect(page.getByTestId("user-menu-trigger")).toContainText("Test User");
  });

  test("profile menu items are clickable and navigate", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page);
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();

    await page.getByTestId("user-menu-trigger").click();
    const panel = page.getByTestId("user-menu-panel");
    await expect(panel).toBeVisible();

    // Click must hit the link, not the chat workspace under the dropdown.
    await panel.getByRole("link", { name: "About" }).click();
    await expect(page).toHaveURL(/\/about$/);
  });
});
