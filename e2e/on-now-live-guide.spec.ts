import { expect, test } from "@playwright/test";
import {
  mockCuratorApis,
  mockFeatures,
  mockLiveChannelsHousehold,
  resetMockCertifications,
} from "./fixtures/api-mocks";

/**
 * Focused dual-watch smoke: Explore What’s on tonight + /live guide when Live is ready.
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

  test("Explore shows What’s on tonight when Live is ready", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/explore");
    await expect(page.getByTestId("explore-page")).toBeVisible();
    await expect(page.getByTestId("whats-on-tonight")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("whats-on-tonight-list")).toBeVisible();
    await expect(page.getByTestId("whats-on-tonight-row").first()).toContainText("Noir Alley");
    await expect(page.getByTestId("whats-on-tonight-watch-cta")).toBeVisible();
    await expect(page.getByTestId("whats-on-tonight-line")).toBeVisible();
  });

  test("Live guide grid renders stations and cells", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/live?mode=guide");
    await expect(page.getByTestId("live-page")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("live-mode-guide")).toBeVisible();
    await expect(page.getByTestId("live-guide")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("live-guide-station").first()).toContainText("Noir Alley");
    await expect(page.getByTestId("live-guide-cell").first()).toContainText("The Big Sleep");
  });
});
