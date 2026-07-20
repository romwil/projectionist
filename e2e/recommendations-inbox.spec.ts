import { expect, test } from "@playwright/test";
import { mockAuthUser, mockCuratorApis, mockFeatures } from "./fixtures/api-mocks";

test("recommendations dismiss only visible cards and expose Play for library titles", async ({ page }) => {
  const dismissedPayloads: unknown[] = [];

  await mockCuratorApis(page);
  await mockFeatures(page, { multi_user_enabled: true });
  await mockAuthUser(page);
  await page.route("**/api/recommendations?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          { id: "brief", media_type: "movie", tmdb_id: 949, rating_key: "plex-949", title: "Heat", message: "Watch this" },
          { id: "other", media_type: "movie", tmdb_id: 680, title: "Pulp Fiction" },
          { id: "detailed", media_type: "movie", tmdb_id: 949, rating_key: "plex-949", title: "Heat", message: "A tense Los Angeles crime classic." },
        ],
      }),
    });
  });
  await page.route("**/api/recommendations/seen", async (route) => {
    dismissedPayloads.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });

  await page.goto("/");

  const inbox = page.getByTestId("recommendations-inbox");
  await expect(inbox).toContainText("2 new recommendations");
  await expect(inbox.getByTestId("recommendation-card-detailed")).toBeVisible();
  await expect(inbox.getByTestId("recommendation-card-brief")).toHaveCount(0);
  await expect(inbox.getByTestId("recommendation-watch-plex")).toBeVisible();

  await inbox.getByTestId("recommendations-dismiss-all").click();
  await expect.poll(() => dismissedPayloads).toEqual([{ ids: ["detailed", "other"] }]);
});
