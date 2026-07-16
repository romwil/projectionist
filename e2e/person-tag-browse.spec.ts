import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

const DETAIL = {
  media_type: "movie",
  title: "Blade Runner",
  year: 1982,
  tmdb_id: 78,
  overview: "A blade runner must pursue replicants.",
  in_library: true,
  rating_key: "plex-78",
  recommendation_reason: "Neo-noir classic",
  runtime_minutes: 117,
  genres: ["Sci-Fi", "Thriller"],
  directors: ["Ridley Scott"],
  cast: ["Harrison Ford"],
  keywords: ["cyberpunk", "dystopia"],
  credits: [
    {
      name: "Ridley Scott",
      tmdb_person_id: 578,
      department: "Directing",
      job: "Director",
      character: "",
      billing_order: 0,
    },
    {
      name: "Harrison Ford",
      tmdb_person_id: 3,
      department: "Acting",
      job: "Actor",
      character: "Deckard",
      billing_order: 0,
    },
  ],
};

async function mockTitleDetail(page: import("@playwright/test").Page) {
  await page.route("**/api/title/movie/78/neighbors**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0 }),
    });
  });
  await page.route("**/api/title/movie/78**", async (route) => {
    if (route.request().url().includes("/neighbors")) {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(DETAIL),
    });
  });
}

test.describe("Person and tag browse", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
  });

  test("title detail cast and tags navigate to person and tag pages", async ({ page }) => {
    await mockTitleDetail(page);
    await page.route("**/api/person/3", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tmdb_person_id: 3,
          name: "Harrison Ford",
          biography: "American actor.",
          known_for_department: "Acting",
          profile_url: "",
          titles: [
            {
              id: 1,
              title: "Blade Runner",
              year: 1982,
              media_type: "movie",
              tmdb_id: 78,
              character: "Deckard",
              poster_url: "",
            },
          ],
          returned: 1,
          in_library_count: 1,
        }),
      });
    });
    await page.route("**/api/library/query**", async (route) => {
      const url = new URL(route.request().url());
      const keywords = url.searchParams.get("keywords") || "";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_matched: keywords.toLowerCase().includes("cyberpunk") ? 1 : 0,
          returned: keywords.toLowerCase().includes("cyberpunk") ? 1 : 0,
          items: keywords.toLowerCase().includes("cyberpunk")
            ? [
                {
                  id: 1,
                  title: "Blade Runner",
                  year: 1982,
                  media_type: "movie",
                  tmdb_id: 78,
                  poster_url: "",
                },
              ]
            : [],
        }),
      });
    });

    await page.goto("/title/movie/78");
    await expect(page.getByTestId("title-detail-page")).toBeVisible();
    await expect(page.getByTestId("title-tag-link").first()).toHaveAttribute("href", "/tag/cyberpunk");
    await expect(page.getByTestId("title-cast-link").first()).toHaveAttribute("href", "/person/3");
    await expect(page.getByTestId("title-genre-link").first()).toHaveAttribute(
      "href",
      "/explore?genre=Sci-Fi",
    );

    await page.getByTestId("title-cast-link").first().click();
    await expect(page).toHaveURL(/\/person\/3$/);
    await expect(page.getByTestId("person-page")).toBeVisible();
    await expect(page.getByTestId("person-name")).toContainText("Harrison Ford");
    await expect(page.getByTestId("person-title-card")).toContainText("Blade Runner");

    await page.goto("/title/movie/78");
    await page.getByTestId("title-tag-link").first().click();
    await expect(page).toHaveURL(/\/tag\/cyberpunk$/);
    await expect(page.getByTestId("tag-page")).toBeVisible();
    await expect(page.getByTestId("tag-name")).toContainText("cyberpunk");
    await expect(page.getByTestId("tag-title-card")).toContainText("Blade Runner");
  });

  test("explore tags hub opens dedicated tag page", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.route("**/api/library/query**", async (route) => {
      const url = new URL(route.request().url());
      const keywords = (url.searchParams.get("keywords") || "").toLowerCase();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_matched: keywords.includes("time loop") ? 1 : 1,
          returned: 1,
          items: [
            {
              id: 9,
              title: keywords.includes("time loop") ? "Primer" : "Alien",
              year: keywords.includes("time loop") ? 2004 : 1979,
              media_type: "movie",
              tmdb_id: keywords.includes("time loop") ? 14337 : 348,
              poster_url: "",
            },
          ],
        }),
      });
    });

    await page.goto("/explore");
    await expect(page.getByTestId("explore-tag-chips")).toBeVisible();
    await page.getByTestId("explore-tag-chip").filter({ hasText: "time loop" }).click();
    await expect(page).toHaveURL(/\/tag\/time%20loop$/);
    await expect(page.getByTestId("tag-page")).toBeVisible();
    await expect(page.getByTestId("tag-title-card")).toContainText("Primer");

    await page.goto("/explore");
    await page.getByTestId("explore-tag-input").fill("found footage");
    await page.getByTestId("explore-tag-submit").click();
    await expect(page).toHaveURL(/\/tag\/found%20footage$/);
  });
});
