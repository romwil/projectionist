import { expect, test } from "@playwright/test";
import {
  mockCuratorApis,
  mockFeatures,
  mockLiveChannelsHousehold,
  resetMockCertifications,
} from "./fixtures/api-mocks";

/**
 * Focused dual-watch smoke: Explore stays library rails; Live guide when Live is ready.
 * Uses API mocks only — not the opt-in live-stack suite.
 */
test.describe("On now + Live guide (mocked)", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockFeatures(page, {
      live_channels_enabled: true,
      live_channels_ready: true,
    });
    await mockLiveChannelsHousehold(page, { enabled: true, ready: true });
  });

  test("Explore omits Live What’s on tonight", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/explore");
    await expect(page.getByTestId("explore-page")).toBeVisible();
    await expect(page.getByTestId("whats-on-tonight")).toHaveCount(0);
  });

  test("Live guide grid renders stations and cells", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/live?mode=guide");
    await expect(page.getByTestId("live-page")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("primary-topbar")).toBeVisible();
    await expect(page.getByTestId("projectionist-brand")).toBeVisible();
    await expect(page.getByTestId("topbar-chat-link")).toBeVisible();
    await expect(page.getByTestId("topbar-explore-link")).toBeVisible();
    await expect(page.getByTestId("topbar-search-link")).toBeVisible();
    await expect(page.getByTestId("app-nav-toggle")).toBeVisible();
    await expect(page.getByTestId("live-mode-guide")).toBeVisible();
    await expect(page.getByTestId("live-mode-watch")).toBeVisible();
    await expect(page.getByTestId("live-guide")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("live-guide-station").first()).toContainText("Noir Alley");
    await expect(page.getByTestId("live-guide-cell").first()).toContainText("The Big Sleep");
  });

  test("iPad and phone keep Guide, Watch, and a way to Chat and Explore", async ({ page }) => {
    async function fitsViewport() {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    }

    await page.setViewportSize({ width: 820, height: 1180 });
    await page.goto("/live?mode=guide");
    await expect(page.getByTestId("live-page")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("projectionist-brand")).toBeVisible();
    await expect(page.getByTestId("live-mode-guide")).toBeVisible();
    await expect(page.getByTestId("live-mode-watch")).toBeVisible();
    await expect(page.getByTestId("topbar-chat-link")).toBeHidden();
    await page.getByTestId("app-nav-toggle").click();
    await expect(page.getByTestId("app-nav-chat")).toBeVisible();
    await expect(page.getByTestId("app-nav-explore")).toBeVisible();
    await expect(page.getByTestId("app-nav-search")).toBeVisible();
    await fitsViewport();

    await page.setViewportSize({ width: 1024, height: 768 });
    await expect(page.getByTestId("topbar-chat-link")).toBeVisible();
    await expect(page.getByTestId("topbar-explore-link")).toBeVisible();
    await expect(page.getByTestId("live-mode-guide")).toBeVisible();
    await fitsViewport();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("projectionist-brand")).toBeVisible();
    await expect(page.getByTestId("live-mode-guide")).toBeVisible();
    await expect(page.getByTestId("live-mode-watch")).toBeVisible();
    await expect(page.getByTestId("app-nav-toggle")).toBeVisible();
    await fitsViewport();
  });
});
