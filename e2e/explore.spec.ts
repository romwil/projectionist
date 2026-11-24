import { expect, test } from "@playwright/test";
import { mockCuratorApis, mockExploreHubPayload, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Explore hub", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test("loads feed rails, pulse, and Related titles hub", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/explore");
    await expect(page.getByTestId("explore-page")).toBeVisible();

    await expect(page.getByTestId("explore-hub-browse-movies")).toBeVisible();
    await expect(page.getByTestId("explore-hub-browse-tv")).toBeVisible();
    await expect(page.getByTestId("explore-hub-related-titles")).toBeVisible();
    await expect(page.getByTestId("explore-hub-tags")).toBeVisible();
    await expect(page.getByTestId("explore-hub-engagement")).toHaveCount(0);
    await expect(page.getByTestId("explore-hub-plot-lab")).toHaveCount(0);

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

    await page.getByTestId("explore-hub-related-titles").click();
    await expect(page).toHaveURL(/\/explore\/related$/);
    await expect(page.getByTestId("related-titles-page")).toBeVisible();
    await expect(page.getByTestId("related-title-seed")).toBeVisible();
    await page.goto("/explore/plot-lab");
    await expect(page).toHaveURL(/\/explore\/related$/);

    await page.goto("/explore");
    // Poster mid-clicks hit always-on Play (1.38+); open the sheet via Actions instead.
    const card = page.getByTestId("explore-recently-added-rail").getByTestId("explore-title-card").first();
    await card.getByRole("button", { name: /Actions for/ }).click();
    await page.getByRole("menu").getByText("Open details").click();
    await expect(page.getByTestId("title-detail-drawer")).toBeVisible();
    await expect(page.getByTestId("title-detail-open-full")).toBeVisible();
    await page.getByTestId("title-detail-open-full").click();
    await expect(page).toHaveURL(/\/title\/movie\/348/);
  });

  test("a poster with art is visible on Explore", async ({ page }) => {
    const art = "/api/library/art/movie/348?id_type=tmdb&kind=poster";
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      "base64",
    );
    const payload = mockExploreHubPayload();
    payload.rails.recently_added.items[0].poster_url = art;
    await page.route("**/api/library/art/**", async (route) => {
      await route.fulfill({ status: 200, contentType: "image/png", body: png });
    });
    await page.route("**/api/library/feeds/hub**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(payload),
      });
    });

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/explore");
    const card = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Alien" }) }).first();
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await expect.poll(async () =>
      card.evaluate((node, relative) => {
        const img = [...node.querySelectorAll("img")].find((el) => el.getAttribute("src") === relative);
        if (!img || img.naturalWidth <= 0) return "hidden";
        return getComputedStyle(img).opacity;
      }, art),
    ).toBe("1");
  });

  test("shelves use a generated poster and the top nav keeps a solid fill", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/explore");
    const card = page.getByRole("article").filter({ has: page.getByRole("heading", { name: /Alien/ }) }).first();
    await expect(card).toBeVisible();
    const poster = await card.evaluate((node) => {
      const art = node.querySelector("[data-motif]");
      if (!art) return null;
      const style = getComputedStyle(art);
      return { motif: art.getAttribute("data-motif"), shadow: style.boxShadow };
    });
    expect(poster?.motif).toMatch(/skyline|road|tower|hills|dunes/);
    expect(poster?.shadow).not.toBe("none");
    const nav = page.getByRole("banner");
    await expect(nav).toBeVisible();
    const paint = await nav.evaluate((node) => getComputedStyle(node).backgroundColor);
    expect(paint).not.toBe("rgba(0, 0, 0, 0)");
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
