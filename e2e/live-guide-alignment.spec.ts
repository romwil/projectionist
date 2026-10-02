import { expect, test, type Page, type Route } from "@playwright/test";
import {
  mockCuratorApis,
  mockFeatures,
  mockLiveChannelsHousehold,
  resetMockCertifications,
} from "./fixtures/api-mocks";

/**
 * Live Guide geometry — header ticks, program cells, now-line and rail rows must
 * share one time scale. Asserts real DOM boxes (not CSS strings).
 */

const SLOT_S = 1800;
const PX_PER_SLOT = 110; // PX_PER_HOUR (220) / 2 in LiveGuide.jsx

/** Deliberately off the half-hour (generated_at = :19:37 past) to catch unsnapped windows. */
function offGridNow(): number {
  const base = Math.floor(Date.now() / 1000 / 3600) * 3600;
  return base + 19 * 60 + 37;
}

async function mockGuide(page: Page, generatedAt: number) {
  const t0 = Math.floor(generatedAt / SLOT_S) * SLOT_S; // grid start (previous :00/:30)
  const prog = (title: string, start: number, stop: number) => ({ title, start, stop });
  const channels = [
    {
      id: "c100",
      name: "Mystery",
      number: 100,
      programs: [
        prog("Law & Order", t0 - 600, t0 + 3600),
        prog("Scorpion", t0 + 3600, t0 + 7200),
        prog("The Lincoln Lawyer", t0 + 7200, t0 + 14400),
      ],
    },
    {
      id: "c101",
      name: "Sci-Fi",
      number: 101,
      programs: [
        prog("Alien vs. Predator", t0 - 3600, t0 + 5400),
        prog("2001: A Space Odyssey", t0 + 5400, t0 + 12600), // 2h film
        prog("Alien: Romulus", t0 + 12600, t0 + 19800),
      ],
    },
    {
      id: "c105",
      // Long name: must not push later rail rows out of step with the grid rows.
      name: "Creature Double Feature (70s Edition) with a very long channel name",
      number: 105,
      programs: [
        prog("Gilligan's Island", t0, t0 + 1800),
        prog("Gilligan's Island", t0 + 1800, t0 + 3600),
        prog("Gilligan's Island", t0 + 3600, t0 + 5400),
        prog("Short bumper", t0 + 5400, t0 + 5700), // 5 min
        prog("Gilligan's Island", t0 + 5700, t0 + 7500),
      ],
    },
  ];
  await page.route("**/api/live-channels/guide**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        enabled: true,
        ready: true,
        generated_at: generatedAt,
        window_seconds: 6 * 3600,
        channels,
      }),
    });
  });
  return { t0, channels };
}

test.describe("Live Guide alignment (mocked)", () => {
  test.beforeEach(async ({ page }) => {
    resetMockCertifications();
    await mockCuratorApis(page);
    await mockFeatures(page, { live_channels_enabled: true, live_channels_ready: true });
    await mockLiveChannelsHousehold(page, { enabled: true, ready: true });
  });

  test("ticks, cells, now-line and rows share one scale", async ({ page }, testInfo) => {
    const generatedAt = offGridNow();
    const { t0 } = await mockGuide(page, generatedAt);
    // Freeze the page clock to the guide's generated_at so the now-line is deterministic.
    await page.clock.install({ time: new Date(generatedAt * 1000) });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/live?mode=guide");
    const guide = page.getByTestId("live-guide");
    await expect(guide).toBeVisible({ timeout: 15_000 });

    const rows = page.getByTestId("live-guide-rows");
    const rowsBox = (await rows.boundingBox())!;
    const ticks = guide.locator(".live-guide-tick");
    const tickCount = await ticks.count();
    expect(tickCount).toBeGreaterThanOrEqual(12);

    // 1. Equal-width columns, no drift to the right edge.
    for (let i = 0; i < tickCount; i += 1) {
      const box = (await ticks.nth(i).boundingBox())!;
      expect(box.x - rowsBox.x).toBeCloseTo(i * PX_PER_SLOT, 0);
      expect(box.width).toBeCloseTo(PX_PER_SLOT, 0);
    }

    // 2. Cells: left edge on start tick, width = duration (checked on the 2h film).
    const cells = guide.getByTestId("live-guide-cell");
    const film = cells.filter({ hasText: "2001: A Space Odyssey" });
    const filmBox = (await film.boundingBox())!;
    expect(filmBox.x - rowsBox.x).toBeCloseTo(((t0 + 5400 - t0) / SLOT_S) * PX_PER_SLOT, 0);
    expect(filmBox.width).toBeCloseTo(4 * PX_PER_SLOT, 0);

    // 3. Cells that start exactly on a tick sit on that tick's header edge.
    const scorpion = (await cells.filter({ hasText: "Scorpion" }).boundingBox())!;
    const tick2 = (await ticks.nth(2).boundingBox())!; // t0 + 1h
    const tick3 = (await ticks.nth(3).boundingBox())!; // t0 + 1h30 (the 2h film)
    expect(Math.abs(scorpion.x - tick2.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(filmBox.x - tick3.x)).toBeLessThanOrEqual(1);
    expect(scorpion.width).toBeCloseTo(2 * PX_PER_SLOT, 0);

    // 4. Short block keeps its true width (5 min = 18.33px), not a 48px minimum.
    const bumper = (await cells.filter({ hasText: "Short bumper" }).boundingBox())!;
    expect(bumper.width).toBeLessThan(25);

    // 5. Now-line sits at generated_at on the same scale and spans every row incl. Weather.
    const nowLine = (await page.getByTestId("live-guide-now-line").boundingBox())!;
    const expectedNowX = ((generatedAt - t0) / 3600) * 220;
    expect(nowLine.x + nowLine.width / 2 - rowsBox.x).toBeCloseTo(expectedNowX, 0);
    expect(nowLine.y).toBeLessThanOrEqual(rowsBox.y + 1);
    expect(nowLine.height).toBeGreaterThanOrEqual(rowsBox.height - 1);

    // 6. Weather block spans the aligned grid (left edge = first tick, right = last).
    const weather = guide.getByTestId("live-guide-row").last().getByTestId("live-guide-cell");
    const weatherBox = (await weather.boundingBox())!;
    expect(weatherBox.x - rowsBox.x).toBeCloseTo(0, 0);
    expect(weatherBox.width).toBeCloseTo(rowsBox.width, 0);

    // 7. Rail stations stay level with their grid rows (even with a 60-char channel name).
    const stations = guide.getByTestId("live-guide-station");
    const gridRows = guide.getByTestId("live-guide-row");
    const n = await gridRows.count();
    expect(await stations.count()).toBe(n);
    for (let i = 0; i < n; i += 1) {
      const s = (await stations.nth(i).boundingBox())!;
      const r = (await gridRows.nth(i).boundingBox())!;
      expect(Math.abs(s.y - r.y)).toBeLessThanOrEqual(1);
      expect(Math.abs(s.height - r.height)).toBeLessThanOrEqual(1);
    }

    await testInfo.attach("guide-aligned", {
      body: await page.screenshot({ fullPage: false }),
      contentType: "image/png",
    });
    await page.screenshot({ path: process.env.GUIDE_SHOT || "test-results/live-guide-aligned.png" });
  });

  test("horizontal scroll moves header and grid together", async ({ page }) => {
    const generatedAt = offGridNow();
    await mockGuide(page, generatedAt);
    await page.setViewportSize({ width: 900, height: 700 });
    await page.goto("/live?mode=guide");
    const guide = page.getByTestId("live-guide");
    await expect(guide).toBeVisible({ timeout: 15_000 });
    const tick = guide.locator(".live-guide-tick").nth(6);
    const cell = guide.getByTestId("live-guide-cell").first();
    const before = {
      tick: (await tick.boundingBox())!.x,
      cell: (await cell.boundingBox())!.x,
    };
    await guide.locator(".live-guide-scroll").evaluate((el) => {
      el.scrollLeft = 300;
    });
    const after = {
      tick: (await tick.boundingBox())!.x,
      cell: (await cell.boundingBox())!.x,
    };
    expect(after.tick - before.tick).toBeCloseTo(after.cell - before.cell, 0);
    expect(before.tick - after.tick).toBeGreaterThan(250);
  });
});
