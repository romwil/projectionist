import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildHouseholdHealthChips, liveReadinessChip } from "./householdHealth.js";

describe("liveReadinessChip", () => {
  it("reports on air when ready", () => {
    const chip = liveReadinessChip({ liveEnabled: true, liveReady: true, stationCount: 4 });
    assert.equal(chip.value, "On air");
    assert.equal(chip.tone, "good");
    assert.match(chip.detail, /4 stations/);
    assert.equal(chip.to, "/admin/live-channels");
  });

  it("reports warming when enabled but not ready", () => {
    const chip = liveReadinessChip({ liveEnabled: true, liveReady: false });
    assert.equal(chip.value, "Warming");
    assert.equal(chip.tone, "warn");
  });

  it("reports off with soft CTA when disabled", () => {
    const chip = liveReadinessChip({ liveEnabled: false });
    assert.equal(chip.value, "Off");
    assert.match(chip.detail, /on the air/i);
  });
});

describe("buildHouseholdHealthChips", () => {
  it("includes Live readiness among household chips", () => {
    const chips = buildHouseholdHealthChips({
      libraryHealth: {
        total: 100,
        unwatched_pct: 40,
        stale_adds: 5,
        rating_coverage_pct: 60,
      },
      libraryStats: { movies: 80, shows: 20, last_sync: "2026-08-01" },
      plexConnected: true,
      sectionsCount: 2,
      liveEnabled: true,
      liveReady: true,
      stationCount: 3,
    });
    const byId = Object.fromEntries(chips.map((c) => [c.id, c]));
    assert.equal(byId.plex.value, "Connected");
    assert.equal(byId.library.value, "100");
    assert.equal(byId.live.value, "On air");
    assert.equal(chips.map((c) => c.id).includes("live"), true);
  });

  it("warns when Plex is missing", () => {
    const chips = buildHouseholdHealthChips({ plexConnected: false });
    assert.equal(chips.find((c) => c.id === "plex")?.tone, "warn");
  });
});
