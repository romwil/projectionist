/**
 * Installable web app. The worker may store the shell. It must not store API, art, or media.
 */
import { expect, test } from "@playwright/test";
import {
  mockAuthUser,
  mockCuratorApis,
  mockFeatures,
  mockSetupStatus,
  resetMockCertifications,
} from "./fixtures/api-mocks";

test.describe("Installable web app", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockSetupStatus(page, {
      onboardingComplete: true,
      radarrOk: true,
      sonarrOk: true,
    });
    await mockFeatures(page, {
      multi_user_enabled: true,
      llm_configured: true,
    });
    await mockAuthUser(page, {
      id: "owner-1",
      display_name: "Household Owner",
      role: "owner",
      default_page: "explore",
    });
  });

  test("manifest, shortcuts, and a service worker that skips API and media", async ({
    page,
  }) => {
    await page.goto("/explore");
    await expect(page.getByTestId("install-projectionist")).toHaveCount(0);

    const manifest = await page.evaluate(async () => {
      const response = await fetch("/manifest.webmanifest");
      return response.json();
    });
    expect(manifest.start_url).toBe("/explore");
    expect(manifest.scope).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.display_override).toContain("window-controls-overlay");
    expect(manifest.shortcuts.map((item: { url: string }) => item.url)).toEqual(
      ["/search", "/explore"],
    );
    expect(manifest.theme_color).toBe("#0c0d11");

    await page.keyboard.press("Control+k");
    await expect(page).toHaveURL(/\/search/);

    await page.goto("/explore");
    await page.waitForFunction(async () => {
      const ready = await navigator.serviceWorker.ready;
      return Boolean(ready.active);
    });
    await page.reload();
    await page.waitForFunction(
      () => navigator.serviceWorker.controller !== null,
    );

    const cached = await page.evaluate(async () => {
      await fetch("/api/features");
      await fetch("/api/playback/sessions/nope/av/stream.m3u8").catch(
        () => undefined,
      );
      await fetch("/api/library/art/movie/1");
      const names = await caches.keys();
      const urls: string[] = [];
      for (const name of names) {
        const cache = await caches.open(name);
        for (const request of await cache.keys())
          urls.push(new URL(request.url).pathname);
      }
      return urls;
    });
    expect(cached.some((path) => path.startsWith("/api"))).toBe(false);
    expect(
      cached.some((path) => path.includes(".m3u8") || path.includes("/art")),
    ).toBe(false);
    expect(cached).toContain("/offline.html");
  });

  test("install stays a quiet settings entry", async ({ page }) => {
    await page.goto("/settings/profile");
    await expect(page.getByTestId("settings-profile")).toBeVisible();
    await expect(page.getByTestId("install-projectionist")).toHaveCount(0);
    await page.evaluate(() => {
      const event = new Event("beforeinstallprompt", { cancelable: true });
      Object.assign(event, {
        prompt: () => Promise.resolve(),
        userChoice: Promise.resolve({ outcome: "dismissed" }),
      });
      window.dispatchEvent(event);
    });
    const entry = page.getByTestId("install-projectionist");
    await expect(entry).toHaveCount(1);
    await expect(entry).toHaveText("Install Projectionist");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});
