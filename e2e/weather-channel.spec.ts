import { expect, test, type Route } from "@playwright/test";
import {
  mockCuratorApis,
  mockFeatures,
  mockLiveChannelsHousehold,
  resetMockCertifications,
} from "./fixtures/api-mocks";

/**
 * Weather Channel (mocked): a Warning paints the bulletin bar and plays first,
 * the chyron stays weather-only, reduced motion freezes the radar on its latest
 * frame, and the browser never synthesizes speech.
 */

const PIXEL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

function payload() {
  return {
    enabled: true,
    place: "Chicago, Illinois",
    latitude: 41.88,
    longitude: -87.63,
    location_source: "household",
    household_place: "Chicago, Illinois",
    country: "US",
    is_us: true,
    error: "",
    boards: {
      current: { temp: 41, feels_like: 35, code: 95, sky: "Thunderstorm", wind: 22, wind_dir: "SW", humidity: 88 },
      hourly: [{ time: "2026-11-04T23:00", label: "11 PM", temp: 41, code: 95, sky: "Thunderstorm", precip: 80 }],
      five_day: [
        { date: "2026-11-05", weekday: "THU", weekday_name: "Thursday", high: 52, low: 38, code: 61, sky: "Light rain", precip: 60 },
      ],
      alerts: {
        supported: true,
        items: [
          {
            id: "w1",
            event: "Severe Thunderstorm Warning",
            severity: "Severe",
            area: "Cook County, IL",
            area_short: "Cook County",
            ends: "2026-11-04T23:45:00-06:00",
            ends_label: "11:45 PM Wednesday",
            headline: "Severe Thunderstorm Warning until 11:45 PM",
            instruction: "Move to an interior room on the lowest floor.",
            sender: "NWS Chicago IL",
            is_warning: true,
          },
        ],
      },
      radar: {
        source: "Iowa Environmental Mesonet NEXRAD",
        marker: { x: 0.5, y: 0.5 },
        frames: Array.from({ length: 6 }, (_, i) => ({ url: PIXEL + "#" + i, time: `2026-11-04T22:${10 + i * 10}:00Z` })),
      },
    },
    segments: [
      { id: "current", label: "Current conditions" },
      { id: "hourly", label: "Next 12 hours" },
      { id: "five_day", label: "5-day forecast" },
      { id: "alerts", label: "Weather bulletin" },
      { id: "radar", label: "Radar" },
      { id: "headlines", label: "Headlines" },
    ],
    local_on_the_8s: ["current", "overview", "hourly"],
    scripts: {
      alerts: [{ text: "This is a weather bulletin.", source: "template", audio_url: "" }],
      current: [{ text: "Forty-one and stormy.", source: "template", audio_url: "" }],
    },
    scripts_version: 1,
    chyron: [
      { group: "NOW", text: "NOW 41° Thunderstorm" },
      { group: "HOURLY", text: "11 PM 41°" },
      { group: "5-DAY", text: "THU 52°/38°" },
    ],
    chyron_summary: "Now 41 degrees with a thunderstorm.",
    headlines: {
      status: "ready",
      scopes: [{ scope: "world", label: "World", items: [{ title: "Unique headline title", source: "BBC News" }] }],
    },
    music: { tracks: [], note: "No soundtrack — the forecast plays without music." },
    muzak: null,
    muzak_note: "No soundtrack — the forecast plays without music.",
    narration: { enabled: false, ready: false },
    egress: [
      { host: "api.open-meteo.com", purpose: "forecast" },
      { host: "api.weather.gov", purpose: "alerts" },
    ],
    preroll_root_found: false,
    intro_preroll: null,
  };
}

test.describe("Weather Channel (mocked)", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockFeatures(page, { live_channels_enabled: true, live_channels_ready: true });
    await mockLiveChannelsHousehold(page, { enabled: true, ready: true });
    await page.route("**/api/live/weather", async (route: Route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload()) });
    });
    await page.addInitScript(() => {
      (window as any).__speechCalls = 0;
      if ("speechSynthesis" in window) {
        window.speechSynthesis.speak = () => {
          (window as any).__speechCalls += 1;
        };
      }
    });
  });

  test("Warning plays first with a bulletin bar; chyron is weather-only; no browser speech", async ({ page }) => {
    await page.goto("/live?mode=weather");
    const channel = page.getByTestId("weather-channel");
    await expect(channel).toBeVisible({ timeout: 15_000 });
    await expect(channel).toHaveAttribute("data-board", "alerts");
    await expect(page.getByTestId("weather-bulletin-bar")).toContainText("Severe Thunderstorm Warning");
    await expect(page.getByTestId("weather-board-alerts")).toContainText("Move to an interior room");
    await expect(page.getByTestId("weather-warning-announcement")).toContainText("Severe Thunderstorm Warning");

    const chyron = page.getByTestId("weather-chyron");
    await expect(chyron).toContainText("NOW 41° Thunderstorm");
    await expect(chyron).toContainText("THU 52°/38°");
    await expect(chyron).not.toContainText("Unique headline title");

    await expect(page.getByTestId("weather-caption")).toContainText("weather bulletin");
    await expect(page.getByTestId("weather-channel-egress")).toContainText("api.weather.gov");
    expect(await page.evaluate(() => (window as any).__speechCalls)).toBe(0);
  });

  test("reduced motion holds the radar on the latest frame", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.clock.install({ time: new Date("2026-11-04T22:01:00") });
    await page.goto("/live?mode=weather");
    const channel = page.getByTestId("weather-channel");
    await expect(channel).toHaveAttribute("data-motion", "reduced", { timeout: 15_000 });
    // Bulletin, then the local block (current, hourly), then the rotation reaches radar.
    for (let i = 0; i < 8; i += 1) {
      if ((await channel.getAttribute("data-board")) === "radar") break;
      await page.clock.runFor(33_000);
    }
    await expect(channel).toHaveAttribute("data-board", "radar");
    const radar = page.getByTestId("weather-radar");
    await expect(radar).toHaveAttribute("data-frame", "5");
    await expect(radar).toHaveAttribute("data-animating", "false");
    await page.clock.runFor(2_000);
    await expect(radar).toHaveAttribute("data-frame", "5");
  });
});
