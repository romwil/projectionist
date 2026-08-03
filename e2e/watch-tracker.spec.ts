import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

test.describe("Watch tracker", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await page.route("**/api/title/movie/78**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          media_type: "movie",
          title: "Blade Runner",
          year: 1982,
          tmdb_id: 78,
          overview: "A blade runner must pursue replicants.",
          in_library: true,
          rating_key: "plex-78",
          view_count: 3,
          genres: ["Science Fiction"],
        }),
      });
    });
  });

  test("shows a user-scoped completion timeline with honest confidence", async ({ page }) => {
    await page.route("**/api/watch-tracker/summary/plex-78", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rating_key: "plex-78",
          tracked_completions: 2,
          completion_confidence: { certain: 1, likely: 0, plex_event_only: 1 },
          logical_viewings: 2,
          sittings_observed: 4,
          tracker_coverage: "partial",
          completion_timeline: [
            {
              completed_at_ms: 1_704_067_800_000,
              confidence: "plex_event_only",
              basis: "unique_played_event",
            },
          ],
        }),
      });
    });

    await page.goto("/title/movie/78");

    const history = page.getByTestId("watch-history");
    await expect(history).toContainText("Your watch history");
    await expect(history).toContainText("2 tracked completions");
    await expect(history).toContainText("Plex played event");
    await history.getByText("Why this count?").click();
    await expect(history).toContainText("does not prove uninterrupted viewing");
  });

  test("labels the legacy Plex fallback when tracker coverage is absent", async ({ page }) => {
    await page.route("**/api/watch-tracker/summary/plex-78", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rating_key: "plex-78",
          tracked_completions: 0,
          completion_confidence: { certain: 0, likely: 0, plex_event_only: 0 },
          tracker_coverage: "none",
          completion_timeline: [],
        }),
      });
    });

    await page.goto("/title/movie/78");

    await expect(page.getByTestId("watch-history-fallback")).toHaveText(
      "Plex marked played 3 times",
    );
  });
});
