/**
 * Household authz e2e (M9): local login, OIDC entrypoint, member Admin deny.
 * Mocked against the Playwright temp server — no live IdP / QA sidecar required.
 */
import { expect, test } from "@playwright/test";
import {
  mockAuthUser,
  mockCuratorApis,
  mockFeatures,
  mockLocalLogin,
  mockOidcAuthorize,
  mockSetupStatus,
  resetMockCertifications,
} from "./fixtures/api-mocks";

test.describe("Household authz", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    // Static setup status avoids the shared mock's route.fetch() race on /admin navigations.
    await mockSetupStatus(page, { onboardingComplete: true, radarrOk: true, sonarrOk: true });
  });

  test("local login reaches chat workspace", async ({ page }) => {
    await mockFeatures(page, {
      multi_user_enabled: true,
      local_login_enabled: true,
      auth_methods: ["local"],
      auth_mode: "local",
    });
    await mockLocalLogin(page, {
      id: "local-1",
      display_name: "Household Local",
      role: "owner",
    });

    await page.goto("/login");
    await expect(page.getByTestId("login-page")).toBeVisible();
    await expect(page.getByTestId("local-login-section")).toBeVisible();
    await page.getByTestId("local-username").fill("house.local");
    await page.getByTestId("local-password").fill("not-a-real-password");
    await page.getByTestId("local-login-submit").click();

    await expect(page).toHaveURL(/\/(chat)?$/);
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("workspace-main")).toBeVisible();
    await expect(page.getByTestId("login-page")).toHaveCount(0);
  });

  test("OIDC button appears and starts authorize redirect", async ({ page }) => {
    await mockFeatures(page, {
      multi_user_enabled: true,
      oidc_enabled: true,
      auth_methods: ["oidc"],
      auth_mode: "oidc",
      oidc_provider_name: "Home IdP",
    });
    await mockOidcAuthorize(page, "https://idp.example.test/authorize?client_id=projectionist");

    await page.goto("/login");
    await expect(page.getByTestId("oidc-login-section")).toBeVisible();
    await expect(page.getByTestId("oidc-login-button")).toContainText("Home IdP");

    // Abort navigation after the authorize call so we stay in Playwright control.
    await page.route("https://idp.example.test/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/plain",
        body: "oidc-authorize-ok",
      });
    });
    await page.getByTestId("oidc-login-button").click();
    await expect(page).toHaveURL(/idp\.example\.test/);
    await expect(page.getByText("oidc-authorize-ok")).toBeVisible();
  });

  test("member has no Admin topbar link and /admin redirects to Settings", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page, {
      id: "member-1",
      display_name: "Household Member",
      role: "member",
    });

    await page.goto("/chat");
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("workspace-main")).toBeVisible();
    await expect(page.getByTestId("topbar-admin-link")).toHaveCount(0);

    await page.goto("/admin");
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByTestId("admin-layout")).toHaveCount(0);
  });

  test("owner still sees Admin and can open the shell", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page, {
      id: "owner-1",
      display_name: "Household Owner",
      role: "owner",
    });

    await page.goto("/chat");
    await page.getByTestId("composer-input").waitFor();
    await expect(page.getByTestId("topbar-admin-link")).toBeVisible();

    await page.getByTestId("topbar-admin-link").click();
    await expect(page).toHaveURL(/\/admin/);
    await expect(page.getByTestId("admin-layout")).toBeVisible({ timeout: 30_000 });
  });
});
