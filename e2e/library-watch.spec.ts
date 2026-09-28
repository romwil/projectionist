import { expect, test } from "@playwright/test";
import { mockCuratorApis, resetMockCertifications } from "./fixtures/api-mocks";

const FIXTURE_M3U8 = `#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:10.0,
seg0.ts
#EXT-X-ENDLIST
`;

async function mockLibraryPlayback(page: import("@playwright/test").Page, extras: Record<string, unknown> = {}) {
  await page.route("**/api/library/playback/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const method = req.method();
    if (method === "POST" && url.pathname.endsWith("/start")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "sess-e2e",
          stream_url: "/api/library/playback/sess-e2e/index.m3u8",
          duration_ms: 3_600_000,
          view_offset_ms: extras.view_offset_ms ?? 0,
          title: "Heat",
          show_title: "",
          season: null,
          episode: null,
          can_resume: Boolean(extras.can_resume),
          next_episode: extras.next_episode ?? null,
          poster_url: "",
          rating_key: "plex-949",
          plex_watch_url: "https://app.plex.tv/desktop/#!/server/mock/details?key=%2Flibrary%2Fmetadata%2Fplex-949",
        }),
      });
      return;
    }
    if (url.pathname.endsWith(".m3u8")) {
      await route.fulfill({
        status: 200,
        contentType: "application/vnd.apple.mpegurl",
        body: FIXTURE_M3U8,
      });
      return;
    }
    if (method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "video/mp2t",
      body: Buffer.from([]),
    });
  });
}

test.describe("In-app library Play", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockLibraryPlayback(page);
  });

  test("Play from title detail opens /watch", async ({ page }) => {
    await page.route("**/api/title/movie/949**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          media_type: "movie",
          title: "Heat",
          year: 1995,
          tmdb_id: 949,
          in_library: true,
          rating_key: "plex-949",
          plex_machine_id: "mock-plex-machine",
        }),
      });
    });

    await page.goto("/title/movie/949");
    await page.getByRole("link", { name: "Play" }).click();
    await expect(page).toHaveURL(/\/watch\/plex-949/);
    await expect(page.getByTestId("watch-theater-shell")).toBeVisible();
    await expect(page.getByTestId("library-player")).toBeVisible();
  });

  test("double-click right third shows +15s chip", async ({ page }) => {
    await page.goto("/watch/plex-949");
    const player = page.getByTestId("library-player");
    await expect(player).toBeVisible();
    const box = await player.boundingBox();
    expect(box).not.toBeNull();
    const x = box!.x + box!.width * 0.85;
    const y = box!.y + box!.height * 0.4;
    await page.mouse.dblclick(x, y);
    await expect(page.getByRole("status")).toContainText("+15s");
  });

  test("pop-out URL and Escape leave the theater", async ({ page }) => {
    await page.goto("/chat");
    await page.goto("/watch/plex-949");
    await expect(page.getByRole("button", { name: "Pop-out" })).toBeVisible();
    await page.goto("/watch/plex-949/popout");
    await expect(page).toHaveURL(/\/watch\/plex-949\/popout/);
    await page.goto("/chat");
    await page.goto("/watch/plex-949");
    await page.getByTestId("library-player").focus();
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(/\/chat/);
  });

  test("resume gate when offset is past two minutes", async ({ page }) => {
    await mockLibraryPlayback(page, { view_offset_ms: 180_000, can_resume: true });
    await page.goto("/watch/plex-949");
    await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Start over" })).toBeVisible();
  });
});
