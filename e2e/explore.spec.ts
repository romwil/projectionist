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

    await expect(page.getByTestId("explore-hub-plot-lab")).toBeVisible();
    await expect(page.getByTestId("explore-hub-tags")).toBeVisible();

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

    await page.getByTestId("explore-hub-plot-lab").click();
    await expect(page).toHaveURL(/\/explore\/plot-lab$/);
    await expect(page.getByTestId("plot-lab-page")).toBeVisible();

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

    await page.goto("/explore");
    await page.getByTestId("explore-recently-added-rail").getByTestId("explore-title-card").first().click();
    await expect(page).toHaveURL(/\/title\/movie\/348/);
  });

  test("deep-linked facet walls use shared browse controls", async ({ page }) => {
    await page.goto("/explore?genre=Sci-Fi");

    const facet = page.getByTestId("explore-section-facet-filter");
    await expect(facet).toContainText("Genre: Sci-Fi");
    await expect(page.getByTestId("explore-facet-toolbar").getByTestId("media-browse-controls")).toBeVisible();
    await expect(page.getByTestId("explore-facet-wall").getByTestId("explore-facet-title-card")).toContainText("Alien");

    await page.getByRole("button", { name: "List" }).click();
    await expect(page).toHaveURL(/genre=Sci-Fi.*view=list|view=list.*genre=Sci-Fi/);

    await page.getByRole("button", { name: "Export CSV" }).click();
    await expect(page.getByRole("button", { name: "Current page · visible columns" })).toBeVisible();
  });

  test("library rail controls expose Play and a viewport-safe action menu", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 700 });
    await page.goto("/explore");

    const card = page.getByTestId("explore-recently-added-rail").getByTestId("explore-title-card").first();
    await expect(card.getByTestId("explore-watch-plex")).toBeVisible();
    await card.getByRole("button", { name: /Actions for/ }).click();

    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByText("Open details")).toBeVisible();
    await expect.poll(() => menu.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return {
        fixed: getComputedStyle(node).position === "fixed",
        visible: rect.top >= 0 && rect.left >= 0 && rect.bottom <= window.innerHeight && rect.right <= window.innerWidth,
      };
    })).toEqual({ fixed: true, visible: true });
  });
});
