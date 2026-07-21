import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildHealthHeroTiles } from "./ownerHealth.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

describe("buildHealthHeroTiles", () => {
  it("derives all six tiles from aggregations", () => {
    const tiles = buildHealthHeroTiles({
      health: {
        total: 1234,
        watched_count: 400,
        unwatched_pct: 68,
        stale_adds: 12,
        rating_coverage_pct: 55,
      },
      coverage: { with_overview_pct: 91 },
      streak: 7,
      openIssues: 3,
    });
    const byId = Object.fromEntries(tiles.map((t) => [t.id, t]));
    assert.equal(byId.titles.value, "1,234");
    assert.equal(byId.unwatched.value, "68%");
    assert.equal(byId.coverage.value, "91%");
    assert.equal(byId.coverage.tone, "good");
    assert.equal(byId.rating.value, "55%");
    assert.equal(byId.issues.value, "3");
    assert.equal(byId.issues.tone, "warn");
    assert.equal(byId.issues.to, "/admin/issues");
    assert.equal(byId.streak.value, "7");
  });

  it("marks issues clear and coverage warn when sparse", () => {
    const tiles = buildHealthHeroTiles({
      health: { total: 10, unwatched_pct: 20 },
      coverage: { with_overview_pct: 30 },
      streak: 0,
      openIssues: 0,
    });
    const byId = Object.fromEntries(tiles.map((t) => [t.id, t]));
    assert.equal(byId.issues.tone, "good");
    assert.equal(byId.issues.detail, "All clear");
    assert.equal(byId.coverage.tone, "warn");
    assert.equal(byId.streak.value, "—");
  });

  it("falls back to em dash on unknown values", () => {
    const tiles = buildHealthHeroTiles({});
    const byId = Object.fromEntries(tiles.map((t) => [t.id, t]));
    assert.equal(byId.titles.value, "—");
    assert.equal(byId.issues.value, "—");
  });
});

describe("owner health hero theme-safe styles", () => {
  it("defines hero tile styles using shared theme tokens (light/dark parity)", () => {
    assert.match(styles, /\.owner-health-hero\b/);
    assert.match(styles, /\.owner-health-tile\b/);
    assert.match(styles, /\.owner-health-tile\.tone-warn\b/);
    assert.match(styles, /\.admin-rail-badge\b/);
  });
});
