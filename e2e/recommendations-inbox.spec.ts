import { expect, test } from "@playwright/test";
import { mockAuthUser, mockCuratorApis, mockFeatures } from "./fixtures/api-mocks";

test("inbox lists notes, opens a library title, and dismisses unread", async ({ page }) => {
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

  const list = page.getByTestId("inbox-list");
  await expect(list.getByTestId("inbox-row-detailed")).toContainText("Heat");
  await expect(list.getByTestId("inbox-row-other")).toContainText("Pulp Fiction");

  await list.getByTestId("inbox-row-detailed").getByRole("button", { name: "Read" }).click();
  const note = page.getByTestId("inbox-note");
  await expect(note.getByTestId("inbox-message-body")).toContainText("A tense Los Angeles crime classic.");
  await expect(note.getByTestId("inbox-open-title")).toBeVisible();

  await note.getByTestId("inbox-note-back").click();
  await list.getByTestId("inbox-dismiss-all").click();
  await expect.poll(() => dismissedPayloads).toEqual([{ all_unread: true }]);
});
