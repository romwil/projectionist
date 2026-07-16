import { expect, test } from "@playwright/test";
import { mockAuthUser, mockCuratorApis, mockFeatures, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Theme chrome", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test("theme toggle sets data-theme on document", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("curatorx.ui_theme", "lights_up");
    });
    await page.route("**/api/auth/me", async (route) => {
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON() as { ui_theme?: string };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            authenticated: true,
            user: {
              id: "bootstrap-owner",
              display_name: "Owner",
              role: "owner",
              ui_theme: body.ui_theme || "lights_up",
              ui_font_size: "medium",
            },
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          authenticated: true,
          user: {
            id: "bootstrap-owner",
            display_name: "Owner",
            role: "owner",
            ui_theme: "lights_up",
            ui_font_size: "medium",
          },
        }),
      });
    });

    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "lights-up");

    // Cycle: lights_up → lights_down → system → lights_up
    await page.getByTestId("topbar-theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "lights-down");

    await page.getByTestId("topbar-theme-toggle").click();
    // system follows OS — only assert the attribute is one of the two themes
    await expect(page.locator("html")).toHaveAttribute("data-theme", /lights-(up|down)/);

    await page.getByTestId("topbar-theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "lights-up");
  });

  test("profile menu stays clickable above workspace", async ({ page }) => {
    await mockFeatures(page, { multi_user_enabled: true });
    await mockAuthUser(page, {
      id: "user-1",
      display_name: "Test User",
      role: "owner",
      ui_theme: "lights_down",
      ui_font_size: "medium",
    });
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();

    const trigger = page.getByTestId("user-menu-trigger");
    await expect(trigger).toBeVisible();
    await trigger.click();
    await expect(page.getByTestId("user-menu-panel")).toBeVisible();
    await expect(page.getByTestId("logout-button")).toBeVisible();
  });

  test("explore icon navigates to explore stub", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
    const explore = page.getByTestId("topbar-explore-link");
    await expect(explore).toBeVisible();
    await explore.click();
    await expect(page.getByTestId("explore-page")).toBeVisible();
  });
});
