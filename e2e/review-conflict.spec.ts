import { expect, test } from "@playwright/test";
import { mockCuratorApis, mockReviewConflictChat, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Review Plex rating conflict", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockReviewConflictChat(page);
    await page.goto("/chat");
    await page.getByTestId("composer-input").waitFor();
  });

  test("renders keep/replace banner when chat includes plex_rating_conflict block", async ({ page }) => {
    await page.getByTestId("composer-input").fill("save my review");
    await page.getByTestId("send-button").click();

    const conflict = page.getByTestId("review-plex-conflict");
    await expect(conflict).toBeVisible();
    await expect(conflict).toContainText("Plex has 3★");
    await expect(conflict.getByTestId("review-keep-plex-rating")).toBeVisible();
    await expect(conflict.getByTestId("review-replace-plex-rating")).toBeVisible();
  });

  test("keep dismisses conflict banner", async ({ page }) => {
    await page.getByTestId("composer-input").fill("save my review");
    await page.getByTestId("send-button").click();

    const conflict = page.getByTestId("review-plex-conflict");
    await expect(conflict).toBeVisible();
    await conflict.getByTestId("review-keep-plex-rating").click();
    await expect(conflict).not.toBeVisible();
  });

  test("replace calls reviews API with replace_plex_rating", async ({ page }) => {
    const reviewRequests: unknown[] = [];
    await page.route("**/api/reviews", async (route) => {
      if (route.request().method() === "POST") {
        reviewRequests.push(route.request().postDataJSON());
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "review-1",
            stars: 5,
            title: "Inception",
            media_type: "movie",
            plex_rating_synced: true,
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.getByTestId("composer-input").fill("save my review");
    await page.getByTestId("send-button").click();

    const conflict = page.getByTestId("review-plex-conflict");
    await conflict.getByTestId("review-replace-plex-rating").click();

    await expect(conflict).not.toBeVisible();
    expect(reviewRequests).toHaveLength(1);
    expect(reviewRequests[0]).toMatchObject({
      stars: 5,
      title: "Inception",
      replace_plex_rating: true,
    });
  });
});
