import { expect, test } from "@playwright/test";
import { mockAuthUser, mockCuratorApis, mockFeatures } from "./fixtures/api-mocks";

test("inbox dismisses visible cards and exposes Play for library titles", async ({ page }) => {
  const dismissedPayloads: unknown[] = [];

  await mockCuratorApis(page);
  await mockFeatures(page, { multi_user_enabled: true });
  await mockAuthUser(page);
  await page.route("**/api/notifications**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "POST" && url.includes("/seen")) {
      dismissedPayloads.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        unread_count: 2,
        items: [
          {
            id: "detailed",
            kind: "recommendation",
            media_type: "movie",
            tmdb_id: 949,
            rating_key: "plex-949",
            title: "Heat",
            message: "A tense Los Angeles crime classic.",
          },
          {
            id: "other",
            kind: "recommendation",
            media_type: "movie",
            tmdb_id: 680,
            title: "Pulp Fiction",
          },
        ],
      }),
    });
  });

  await page.goto("/inbox");
  await expect(page.getByTestId("inbox-page")).toBeVisible();

  const inbox = page.getByTestId("recommendations-inbox");
  await expect(inbox).toContainText("2 new notifications");
  await expect(inbox.getByTestId("recommendation-card-detailed")).toBeVisible();
  await expect(inbox.getByTestId("recommendation-card-other")).toBeVisible();
  await expect(inbox.getByTestId("recommendation-watch-plex")).toBeVisible();

  await inbox.getByTestId("recommendations-dismiss-all").click();
  await expect.poll(() => dismissedPayloads).toEqual([{ ids: ["detailed", "other"] }]);
});
