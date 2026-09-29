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
  // Oversized poster dimension (not a real bitmap) — layout must not use intrinsic size.
  const hugePoster =
    typeof extras.poster_url === "string"
      ? extras.poster_url
      : "data:image/svg+xml," +
        encodeURIComponent(
          `<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="3600"><rect width="100%" height="100%" fill="#2a6ebb"/><text x="50%" y="50%" fill="#fff" font-size="220" text-anchor="middle">POSTER</text></svg>`,
        );
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
          poster_url: hugePoster,
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

  test("theater stays viewport-bound even with a huge poster", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/watch/plex-949");
    const shell = page.getByTestId("watch-theater-shell");
    await expect(shell).toBeVisible();
    const metrics = await page.evaluate(() => {
      const el = document.querySelector("[data-testid='watch-theater-shell']");
      const video = document.querySelector("[data-testid='library-player-video']");
      const poster = document.querySelector("[data-testid='library-player-stage-poster']");
      if (!el || !video) return null;
      const shellBox = el.getBoundingClientRect();
      const videoBox = video.getBoundingClientRect();
      const posterBox = poster?.getBoundingClientRect();
      return {
        shellH: shellBox.height,
        shellW: shellBox.width,
        videoH: videoBox.height,
        videoW: videoBox.width,
        posterH: posterBox?.height ?? 0,
        docScrollH: document.documentElement.scrollHeight,
        innerH: window.innerHeight,
        innerW: window.innerWidth,
      };
    });
    expect(metrics).not.toBeNull();
    expect(metrics!.shellH).toBeLessThanOrEqual(metrics!.innerH + 1);
    expect(metrics!.shellW).toBeLessThanOrEqual(metrics!.innerW + 1);
    expect(metrics!.videoH).toBeLessThanOrEqual(metrics!.innerH + 1);
    expect(metrics!.videoW).toBeLessThanOrEqual(metrics!.innerW + 1);
    expect(metrics!.posterH).toBeLessThanOrEqual(metrics!.innerH + 1);
    expect(metrics!.docScrollH).toBeLessThanOrEqual(metrics!.innerH + 2);
    await expect(page.getByTestId("library-play-toggle")).toBeVisible();
    // Center play shows when paused; autoplay may already be "playing" in Chromium.
    const center = page.getByTestId("library-center-play");
    if (await center.count()) {
      await expect(center).toBeVisible();
    }
  });

  test("Play button is actionable on the OSD", async ({ page }) => {
    await page.goto("/watch/plex-949");
    const playBtn = page.getByTestId("library-play-toggle");
    await expect(playBtn).toBeVisible();
    await playBtn.click();
    await expect(playBtn).toBeEnabled();
    await expect(page.getByTestId("library-player-error")).toHaveCount(0);
  });

  test("phone 390 keeps theater inside the viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/watch/plex-949");
    const metrics = await page.evaluate(() => {
      const el = document.querySelector("[data-testid='watch-theater-shell']");
      const video = document.querySelector("[data-testid='library-player-video']");
      if (!el || !video) return null;
      return {
        shellH: el.getBoundingClientRect().height,
        videoH: video.getBoundingClientRect().height,
        docScrollH: document.documentElement.scrollHeight,
        innerH: window.innerHeight,
        phone: document.querySelector(".library-watch")?.getAttribute("data-play-phone"),
      };
    });
    expect(metrics).not.toBeNull();
    expect(metrics!.shellH).toBeLessThanOrEqual(metrics!.innerH + 1);
    expect(metrics!.videoH).toBeLessThanOrEqual(metrics!.innerH + 1);
    expect(metrics!.docScrollH).toBeLessThanOrEqual(metrics!.innerH + 2);
    expect(metrics!.phone).toBe("true");
    await expect(page.getByTestId("library-osd-more")).toBeVisible();
    await expect(page.getByRole("button", { name: "Pop-out" })).toHaveCount(0);
  });

  test("phone landscape keeps OSD transport inside the safe viewport", async ({ page }) => {
    // iPhone-class landscape — width is the long edge (unreachable under old max-width:390 rules).
    await page.setViewportSize({ width: 844, height: 390 });
    await page.goto("/watch/plex-949");
    await expect(page.getByTestId("library-player")).toBeVisible();
    await expect(page.locator(".library-watch")).toHaveAttribute("data-play-phone", "true");

    // Nudge OSD visible (idle may hide it).
    await page.getByTestId("library-player").click({ position: { x: 40, y: 40 } });
    const transport = page.getByTestId("library-osd-transport");
    await expect(transport).toBeVisible();
    await expect(page.getByTestId("library-skip-forward")).toBeVisible();
    await expect(page.getByTestId("library-play-toggle")).toBeVisible();

    const layout = await page.evaluate(() => {
      const shell = document.querySelector("[data-testid='watch-theater-shell']");
      const osd = document.querySelector("[data-testid='library-player-osd']");
      const transportEl = document.querySelector("[data-testid='library-osd-transport']");
      const skip = document.querySelector("[data-testid='library-skip-forward']");
      const play = document.querySelector("[data-testid='library-play-toggle']");
      if (!shell || !osd || !transportEl || !skip || !play) return null;
      const shellBox = shell.getBoundingClientRect();
      const osdBox = osd.getBoundingClientRect();
      const transportBox = transportEl.getBoundingClientRect();
      const skipBox = skip.getBoundingClientRect();
      const playBox = play.getBoundingClientRect();
      return {
        shellBottom: shellBox.bottom,
        osdBottom: osdBox.bottom,
        transportBottom: transportBox.bottom,
        skipH: skipBox.height,
        skipW: skipBox.width,
        playH: playBox.height,
        playW: playBox.width,
        transportFullyInShell:
          transportBox.top >= shellBox.top - 1 &&
          transportBox.bottom <= shellBox.bottom + 1 &&
          transportBox.left >= shellBox.left - 1 &&
          transportBox.right <= shellBox.right + 1,
      };
    });
    expect(layout).not.toBeNull();
    expect(layout!.transportFullyInShell).toBe(true);
    expect(layout!.osdBottom).toBeLessThanOrEqual(layout!.shellBottom + 1);
    expect(layout!.skipH).toBeGreaterThanOrEqual(43);
    expect(layout!.skipW).toBeGreaterThanOrEqual(43);
    expect(layout!.playH).toBeGreaterThanOrEqual(43);
    expect(layout!.playW).toBeGreaterThanOrEqual(43);
    await expect(page.getByRole("button", { name: "Pop-out" })).toHaveCount(0);
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
    await expect(page.getByTestId("library-skip-chip")).toContainText("+15s");
  });

  test("More menu exposes Pop-out; Escape leaves the theater", async ({ page }) => {
    await page.goto("/chat");
    await page.goto("/watch/plex-949");
    await page.getByTestId("library-osd-more").click();
    await expect(page.getByTestId("library-osd-menu")).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Pop-out" })).toBeVisible();
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

  test("watch does not thrash HLS playlist fetches after status ticks", async ({ page }) => {
    let m3u8Hits = 0;
    page.on("request", (req) => {
      if (req.url().includes("/api/library/playback/") && req.url().includes(".m3u8")) {
        m3u8Hits += 1;
      }
    });
    await page.goto("/watch/plex-949");
    await expect(page.getByTestId("library-player")).toBeVisible();
    // Allow status loading→ready→playing ticks; a remount loop would explode this count.
    await page.waitForTimeout(2000);
    expect(m3u8Hits).toBeGreaterThan(0);
    expect(m3u8Hits).toBeLessThan(8);
    await expect(page.getByTestId("library-player-error")).toHaveCount(0);
  });

  test("show seasons episode Play opens /watch; title opens episode detail", async ({ page }) => {
    await page.route("**/api/title/show/43323**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          media_type: "show",
          title: "Between Two Ferns",
          year: 2012,
          tmdb_id: 43323,
          in_library: true,
          rating_key: "show-rk",
          library_item_id: 42,
          plex_machine_id: "mock-plex-machine",
        }),
      });
    });
    await page.route("**/api/library/tv/seasons**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          show_id: 42,
          show_title: "Between Two Ferns",
          total_seasons: 1,
          total_episodes: 1,
          file_size_bytes: 1000,
          seasons: [
            {
              season_number: 1,
              episode_count: 1,
              watched_count: 0,
              file_size_bytes: 1000,
              episodes: [
                {
                  id: 1,
                  rating_key: "ep-fern-1",
                  season_number: 1,
                  episode_number: 1,
                  title: "Zach Galifianakis",
                  view_count: 0,
                  runtime_minutes: 22,
                  file_size: 500,
                },
              ],
            },
          ],
        }),
      });
    });
    await page.route("**/api/watch-tracker/shows/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ hasCoverage: false, timeline: [], episode_completions: {} }),
      });
    });
    await page.route("**/api/library/tv/episode/ep-fern-1**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          media_type: "episode",
          episode: {
            rating_key: "ep-fern-1",
            title: "Zach Galifianakis",
            season_number: 1,
            episode_number: 1,
            runtime_minutes: 22,
            unwatched: true,
            aired_at: "2012-01-01",
          },
          show: {
            id: 42,
            title: "Between Two Ferns",
            tmdb_id: 43323,
            poster_url: "",
          },
          prev_episode: null,
          next_episode: null,
        }),
      });
    });

    await page.goto("/title/show/43323");
    await expect(page.getByTestId("show-seasons-panel")).toBeVisible();
    await expect(page.getByTestId("show-episode-play-ep-fern-1")).toBeVisible();
    await page.getByTestId("show-episode-title-ep-fern-1").click();
    await expect(page).toHaveURL(/\/title\/episode\/ep-fern-1/);
    await expect(page.getByTestId("episode-detail-play")).toBeVisible();
    await page.getByTestId("episode-detail-play").click();
    await expect(page).toHaveURL(/\/watch\/ep-fern-1/);
    await expect(page.getByTestId("library-player")).toBeVisible();

    await page.goto("/title/show/43323");
    await page.getByTestId("show-episode-play-ep-fern-1").click();
    await expect(page).toHaveURL(/\/watch\/ep-fern-1/);
  });
});
