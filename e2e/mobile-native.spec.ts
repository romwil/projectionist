import { expect, test } from "@playwright/test";
import { mockCuratorApis, mockFeatures, mockLiveChannelsHousehold, resetMockCertifications } from "./fixtures/api-mocks";
import { completeOnboardingViaApi } from "./fixtures/helpers";
import {
  NATIVE_VIEWPORT,
  assertMinTapSize,
  assertNoHorizontalPageOverflow,
  assertPinnedNearViewportBottom,
  computedOverflowY,
  measureRail,
  swipeRail,
} from "./fixtures/nativeMobile";

const RAIL_TITLES = [
  { id: 11, title: "Heat", year: 1995, media_type: "movie", tmdb_id: 949, rating_key: "plex-949", poster_url: "" },
  { id: 12, title: "Alien", year: 1979, media_type: "movie", tmdb_id: 348, rating_key: "plex-348", poster_url: "" },
  { id: 13, title: "Blade Runner", year: 1982, media_type: "movie", tmdb_id: 78, rating_key: "plex-78", poster_url: "" },
  { id: 14, title: "Chinatown", year: 1974, media_type: "movie", tmdb_id: 829, rating_key: "plex-829", poster_url: "" },
];

function neighborEdge(peer: (typeof RAIL_TITLES)[number], toId: number) {
  return {
    relation: "neighbor",
    to_id: toId,
    peer: { ...peer, in_library: true },
    why: { label: "Strong plot kinship", surprise_flavor: null },
  };
}

/**
 * Native-mobile UX contract at iPhone-class 390×844.
 * Dual-role: living-room member surfaces + admin chrome.
 * Mocked e2e on 8799 only — never prod :8788.
 */
test.describe("Native mobile — member living-room", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockFeatures(page, { live_channels_enabled: true, live_channels_ready: true });
    await mockLiveChannelsHousehold(page, { enabled: true, ready: true });
  });

  test("chat composer is sticky, 16px, 44px send, no page overflow", async ({ page }) => {
    await page.goto("/");
    const input = page.getByTestId("composer-input");
    await input.waitFor();

    await assertNoHorizontalPageOverflow(page);
    await assertMinTapSize(page.getByTestId("send-button"));
    await expect(input).toHaveCSS("font-size", "16px");

    const composer = page.locator("form.composer");
    await expect(composer).toBeVisible();
    await assertPinnedNearViewportBottom(composer, NATIVE_VIEWPORT.height);

    const brand = page.getByTestId("projectionist-brand");
    await expect(brand).toContainText("Projectionist");
    const wordmark = await brand.evaluate((el) => {
      const h1 = el.querySelector("h1");
      return {
        text: h1?.textContent?.replace(/\s+/g, " ").trim() || "",
        scrollWidth: h1?.scrollWidth ?? 0,
        clientWidth: h1?.clientWidth ?? 0,
      };
    });
    expect(wordmark.text).toMatch(/Projectionist/);
    expect(wordmark.scrollWidth).toBeLessThanOrEqual(wordmark.clientWidth + 1);

    const thread = page.getByTestId("chat-scroll-region");
    const threadBox = await thread.boundingBox();
    expect(threadBox, "thread should occupy the middle pane").not.toBeNull();
    expect(threadBox!.height).toBeGreaterThan(200);

    await expect(page.getByTestId("app-topbar-peers")).toBeHidden();

    await input.fill("Find neo-noir films");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-user")).toContainText("Find neo-noir films");
    await expect(page.getByTestId("send-button")).toBeVisible();
    await assertPinnedNearViewportBottom(composer, NATIVE_VIEWPORT.height);
  });

  test("short Simple Browser pane still shows composer and full wordmark", async ({ page }) => {
    await page.setViewportSize({ width: 560, height: 640 });
    await page.goto("/");
    const composer = page.locator("form.composer");
    await expect(composer).toBeVisible();
    await assertPinnedNearViewportBottom(composer, 640, 48);
    const brand = page.getByTestId("projectionist-brand");
    await expect(brand).toContainText("Projectionist");
    const wordmark = await brand.evaluate((el) => {
      const h1 = el.querySelector("h1");
      return {
        scrollWidth: h1?.scrollWidth ?? 0,
        clientWidth: h1?.clientWidth ?? 0,
      };
    });
    expect(wordmark.scrollWidth).toBeLessThanOrEqual(wordmark.clientWidth + 1);
    const threadBox = await page.getByTestId("chat-scroll-region").boundingBox();
    expect(threadBox!.height).toBeGreaterThan(160);
    await expect(page.getByTestId("app-topbar-peers")).toBeHidden();
    await assertNoHorizontalPageOverflow(page);
  });

  test("420×480 Simple Browser: composer input stays in the pane (not 100vh-clipped)", async ({ page }) => {
    await page.setViewportSize({ width: 420, height: 480 });
    await page.goto("/");
    const composer = page.locator("form.composer");
    const input = page.getByTestId("composer-input");
    await expect(composer).toBeVisible();
    await expect(input).toBeVisible();
    await assertPinnedNearViewportBottom(composer, 480, 56);
    const metrics = await page.evaluate(() => {
      const root = document.querySelector(".app-root.workspace");
      const form = document.querySelector("form.composer");
      const field = document.querySelector("[data-testid='composer-input']");
      const cs = root ? getComputedStyle(root) : null;
      const formBox = form?.getBoundingClientRect();
      const inputBox = field?.getBoundingClientRect();
      return {
        minHeight: cs?.minHeight,
        height: cs?.height,
        maxHeight: cs?.maxHeight,
        innerHeight,
        formTop: formBox?.top ?? -1,
        formBottom: formBox?.bottom ?? -1,
        inputTop: inputBox?.top ?? -1,
        inputBottom: inputBox?.bottom ?? -1,
        inputHeight: inputBox?.height ?? 0,
      };
    });
    expect(parseFloat(metrics.minHeight || "0")).toBeLessThanOrEqual(metrics.innerHeight);
    expect(parseFloat(metrics.height || "0")).toBeLessThanOrEqual(metrics.innerHeight + 1);
    expect(metrics.formTop).toBeGreaterThanOrEqual(0);
    expect(metrics.formBottom).toBeLessThanOrEqual(metrics.innerHeight + 4);
    expect(metrics.inputTop).toBeGreaterThanOrEqual(0);
    expect(metrics.inputBottom).toBeLessThanOrEqual(metrics.innerHeight + 4);
    expect(metrics.inputHeight).toBeGreaterThan(20);
    const threadBox = await page.getByTestId("chat-scroll-region").boundingBox();
    expect(threadBox, "thread should keep a usable middle pane").not.toBeNull();
    expect(threadBox!.height).toBeGreaterThan(80);
  });

  test("user turn stays visible and New reply chip sits above the composer", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
    await page.getByTestId("composer-input").fill("I asked about Chinatown");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-user")).toContainText("I asked about Chinatown");

    const workspace = page.getByTestId("workspace-main");
    const html = await workspace.innerHTML();
    const scrollAt = html.indexOf("chat-scroll-region");
    const composerAt = html.indexOf('class="composer');
    expect(scrollAt).toBeGreaterThanOrEqual(0);
    expect(composerAt).toBeGreaterThan(scrollAt);

    const region = page.getByTestId("chat-scroll-region");
    await region.evaluate((el) => {
      el.scrollTop = 0;
    });
    await page.waitForTimeout(50);
    const chip = page.getByTestId("new-reply-chip");
    if (await chip.count()) {
      const chipBox = await chip.boundingBox();
      const composerBox = await page.locator("form.composer").boundingBox();
      expect(chipBox).not.toBeNull();
      expect(composerBox).not.toBeNull();
      expect(chipBox!.y + chipBox!.height).toBeLessThanOrEqual(composerBox!.y + 2);
      await assertMinTapSize(chip);
    }
  });

  test("library browse posters open a sheet overlay without overflowing", async ({ page }) => {
    await page.goto("/search");
    await expect(page.getByTestId("library-browse-results")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Browse library" })).toHaveCount(0);
    await expect(page.getByText("Every title in your library")).toHaveCount(0);
    await expect(page.getByTestId("library-browse-search-input")).toBeVisible();
    await expect(page.getByTestId("app-shell-page-bar")).toHaveCount(0);
    const filters = page.getByTestId("library-browse-filters");
    await expect(filters).toBeVisible();
    await expect(filters).not.toHaveAttribute("open");
    await assertNoHorizontalPageOverflow(page);

    const card = page.getByTestId("library-browse-card").first();
    await expect(card).toBeVisible();
    await card.locator(".explore-cinema-card-link").click();

    const drawer = page.getByTestId("title-detail-drawer");
    await expect(drawer).toBeVisible();
    const box = await drawer.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(NATIVE_VIEWPORT.width + 1);
    await assertMinTapSize(page.getByTestId("title-detail-drawer-close"));
    await page.getByTestId("title-detail-drawer-close").click();
    await expect(drawer).toHaveCount(0);
  });

  test("explore card rails swipe horizontally without nested vertical scroll", async ({ page }) => {
    await page.route("**/api/library/feeds/continue-watching**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          feed: "continue-watching",
          total: RAIL_TITLES.length,
          note: null,
          items: RAIL_TITLES,
        }),
      });
    });

    await page.goto("/explore");
    const rail = page.getByTestId("explore-continue-watching-rail");
    await expect(rail).toBeVisible();
    const before = await measureRail(rail);
    expect(before.overflowX).toBe("auto");
    expect(before.overflowY).toBe("hidden");
    expect(before.canScrollX).toBeTruthy();
    expect(before.scrollLeft).toBe(0);

    const swipe = await swipeRail(rail, 200);
    expect(swipe.after).toBeGreaterThan(swipe.before);
    expect(swipe.pageDelta).toBe(0);
    const after = await measureRail(rail);
    expect(after.scrollLeft).toBeGreaterThan(0);
    expect(after.overflowY).toBe("hidden");
  });

  test("phone title sheet shows a swipeable More like this rail", async ({ page }) => {
    await page.route("**/api/title/movie/348**", async (route) => {
      const url = route.request().url();
      if (url.includes("/relations") || url.includes("/neighbors")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [
              neighborEdge(RAIL_TITLES[0], 11),
              neighborEdge(RAIL_TITLES[2], 13),
              neighborEdge(RAIL_TITLES[3], 14),
            ],
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          media_type: "movie",
          title: "Alien",
          year: 1979,
          tmdb_id: 348,
          overview: "In space no one can hear you scream.",
          in_library: true,
          rating_key: "plex-348",
        }),
      });
    });

    await page.goto("/search");
    await expect(page.getByTestId("library-browse-results")).toBeVisible();
    await page.getByTestId("library-browse-card").first().locator(".explore-cinema-card-link").click();
    const drawer = page.getByTestId("title-detail-drawer");
    await expect(drawer).toBeVisible();
    const track = drawer.locator(".title-neighbors-track").first();
    await expect(page.getByTestId("title-neighbors")).toBeVisible();
    await expect(track).toBeVisible();
    const before = await measureRail(track);
    expect(before.overflowX).toBe("auto");
    expect(before.overflowY).toBe("hidden");
    expect(before.canScrollX).toBeTruthy();
    const swipe = await swipeRail(track, 160);
    expect(swipe.after).toBeGreaterThan(swipe.before);
  });

  test("Live watch chrome is thumb-reachable and does not bounce horizontally", async ({ page }) => {
    await page.goto("/live?mode=watch");
    await expect(page.getByTestId("live-page").or(page.getByTestId("live-watch-page"))).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("live-chrome")).toBeVisible();
    await assertNoHorizontalPageOverflow(page);
    const watch = page.getByTestId("live-mode-watch");
    if (await watch.count()) {
      await assertMinTapSize(watch);
    }
  });

  test("member notifications inputs stay 16px with 44px save", async ({ page }) => {
    await page.goto("/settings/notifications");
    await expect(page.getByTestId("settings-notifications")).toBeVisible();
    const email = page.getByTestId("notifications-email-input");
    await expect(email).toBeVisible();
    await expect(email).toHaveCSS("font-size", "16px");
    await assertMinTapSize(page.getByTestId("notifications-save"));
    await assertNoHorizontalPageOverflow(page);
  });
});

test.describe("Native mobile — admin pass", () => {
  test.beforeEach(async ({ page, request }) => {
    resetMockCertifications();
    await completeOnboardingViaApi(request);
    await mockCuratorApis(page);
    await mockFeatures(page, { live_channels_enabled: true, live_channels_ready: true });
    await mockLiveChannelsHousehold(page, { enabled: true, ready: true });
  });

  test("Overview keeps one gold primary and does not overflow", async ({ page }) => {
    await page.goto("/admin/overview");
    await page.getByTestId("household-health-hero").waitFor();
    await assertNoHorizontalPageOverflow(page);
    await expect(page.getByTestId("household-health-hero")).toBeVisible();
    await expect(page.getByTestId("projectionist-brand")).toContainText("Projectionist");

    const grid = page.getByTestId("household-health-grid");
    const cols = await grid.evaluate((el) => getComputedStyle(el).gridTemplateColumns);
    expect(cols.split(" ").length, "narrow Overview tiles should be 2-col").toBeLessThanOrEqual(2);

    const gold = page.locator(".service-card-actions .primary, .service-card-actions button.primary");
    if (await gold.count()) {
      await assertMinTapSize(gold.first());
    }
  });

  test("Libraries mapping is reachable at 44px without 100vw bounce", async ({ page }) => {
    await page.goto("/admin/libraries");
    await expect(page.getByTestId("plex-library-mapping")).toBeVisible();
    await assertNoHorizontalPageOverflow(page);
    const navToggle = page.getByTestId("app-nav-toggle");
    await expect(navToggle).toBeVisible();
    await assertMinTapSize(navToggle);
    await navToggle.click();
    await expect(page.getByTestId("app-nav-drawer")).toBeVisible();
    await expect(page.getByTestId("app-nav-admin-libraries")).toBeVisible();
  });

  test("Live Channels admin tabs meet 44px and stay on-canvas", async ({ page }) => {
    await page.goto("/admin/live-channels");
    const settings = page.getByTestId("live-channels-settings");
    await expect(settings.or(page.getByTestId("live-channels-tabs"))).toBeVisible({ timeout: 15_000 });
    await assertNoHorizontalPageOverflow(page);
    const tab = page.getByTestId("live-channels-tab-stations");
    if (await tab.count()) {
      await assertMinTapSize(tab);
      await tab.click();
    }
    const notes = page.locator(".wizard-note").first();
    if (await notes.count()) {
      await expect(notes).toHaveCSS("font-size", "14px");
    }
  });

  test("completed chat poster strips do not nest a vertical scrollbar", async ({ page }) => {
    await page.route("**/api/chat/stream**", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      const url = new URL(route.request().url());
      const sessionId = url.searchParams.get("session_id") || "mobile-admin-cards";
      const payload = {
        type: "done",
        session_id: sessionId,
        message: {
          id: "assistant-cards",
          role: "assistant",
          blocks: [
            { type: "text", content: "Here are some picks." },
            {
              type: "title_cards",
              items: [
                { media_type: "movie", title: "Blade Runner", year: 1982, tmdb_id: 78, poster_url: "", in_library: false },
                { media_type: "movie", title: "Chinatown", year: 1974, tmdb_id: 829, poster_url: "", in_library: false },
                { media_type: "movie", title: "Heat", year: 1995, tmdb_id: 949, poster_url: "", in_library: false },
              ],
            },
          ],
          created_at: Math.floor(Date.now() / 1000),
          lens_id: "general",
        },
        pending_tokens: [],
      };
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: done\ndata: ${JSON.stringify(payload)}\n\n`,
      });
    });

    await page.goto("/");
    await page.getByTestId("composer-input").waitFor();
    await page.getByTestId("composer-input").fill("recommend neo-noir");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-assistant")).toContainText("Blade Runner");
    const strip = page.locator(".chat-scroll-region .inline-cards").first();
    await expect(strip).toBeVisible();
    expect(await computedOverflowY(strip)).toBe("hidden");
    const before = await measureRail(strip);
    expect(before.overflowX).toBe("auto");
    expect(before.canScrollX).toBeTruthy();
    const swipe = await swipeRail(strip, 180);
    expect(swipe.after).toBeGreaterThan(swipe.before);
  });
});
