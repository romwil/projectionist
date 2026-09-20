import { expect, test } from "@playwright/test";
import { mockCuratorApis, mockFeatures, mockLiveChannelsHousehold, resetMockCertifications } from "./fixtures/api-mocks";
import { completeOnboardingViaApi } from "./fixtures/helpers";
import {
  NATIVE_VIEWPORT,
  assertMinTapSize,
  assertNoHorizontalPageOverflow,
  assertPinnedNearViewportBottom,
  computedOverflowY,
} from "./fixtures/nativeMobile";

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

    await input.fill("Find neo-noir films");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("chat-message-user")).toContainText("Find neo-noir films");
    await expect(page.getByTestId("send-button")).toBeVisible();
    await assertPinnedNearViewportBottom(composer, NATIVE_VIEWPORT.height);
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
  });
});
