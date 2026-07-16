import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Explore hub", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test("loads feed rails, pulse, and plot lab motifs", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/explore");
    await expect(page.getByTestId("explore-page")).toBeVisible();

    await expect(page.getByTestId("explore-recently-added-rail")).toBeVisible();
    await expect(page.getByTestId("explore-recently-added-rail").getByTestId("explore-title-card")).toContainText(
      "Alien",
    );

    await expect(page.getByTestId("explore-section-recent-releases")).toContainText(
      "No library titles released in the last 90 days.",
    );

    await expect(page.getByTestId("explore-pulse-grid")).toBeVisible();
    await expect(page.getByTestId("explore-pulse-total")).toBeVisible();

    await expect(page.getByTestId("explore-on-this-day-rail")).toBeVisible();
    await expect(page.getByTestId("explore-on-this-day-rail")).toContainText("Jaws");

    await expect(page.getByTestId("explore-motif-chips")).toBeVisible();
    const chip = page.getByTestId("explore-motif-chip").first();
    await chip.click();
    await expect(page.getByTestId("explore-motif-wall")).toBeVisible();
    await expect(page.getByTestId("explore-motif-wall").getByTestId("explore-title-card")).toContainText("Alien");

    await page.getByTestId("explore-seed-input").fill("Alien");
    await expect(page.getByTestId("explore-seed-hits")).toBeVisible();
    await page.getByTestId("explore-seed-hits").getByRole("button").first().click();
    await expect(page.getByTestId("explore-seed-active")).toContainText("Alien");
    await expect(page.getByTestId("explore-neighbors-rail")).toContainText("The Thing");

    await page.getByTestId("explore-recently-added-rail").getByTestId("explore-title-card").first().click();
    await expect(page).toHaveURL(/\/title\/movie\/348/);
  });
});
