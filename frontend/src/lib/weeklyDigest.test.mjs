import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatDigestTitle, normalizeWeeklyDigest } from "./weeklyDigest.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

describe("normalizeWeeklyDigest", () => {
  it("returns null when there is no digest", () => {
    assert.equal(normalizeWeeklyDigest(null), null);
    assert.equal(normalizeWeeklyDigest(undefined), null);
  });

  it("maps a digest payload into a display model", () => {
    const model = normalizeWeeklyDigest({
      generated_at: 1000,
      week_start: 900,
      payload: {
        library: { total: 500, movies: 300, shows: 200 },
        new_this_week: {
          count: 4,
          titles: [{ title: "Ran", year: 1985, media_type: "movie" }],
        },
        health: { unwatched_pct: 62.4, stale_adds: 8, rating_coverage_pct: 40 },
        coverage: { with_overview_pct: 88.6 },
        issues: { open: 2 },
        purge: { candidates: 6 },
      },
    });
    assert.equal(model.generatedAt, 1000);
    assert.equal(model.library.total, 500);
    assert.equal(model.newCount, 4);
    assert.equal(model.newTitles.length, 1);
    const stats = Object.fromEntries(model.stats.map((s) => [s.id, s.value]));
    assert.equal(stats.new, "4");
    assert.equal(stats["open-issues"], "2");
    assert.equal(stats.unwatched, "62%");
    assert.equal(stats.coverage, "89%");
    assert.equal(stats.purge, "6");
  });

  it("tolerates empty payloads", () => {
    const model = normalizeWeeklyDigest({ generated_at: 5, payload: {} });
    assert.equal(model.library.total, 0);
    assert.equal(model.newTitles.length, 0);
    const stats = Object.fromEntries(model.stats.map((s) => [s.id, s.value]));
    assert.equal(stats.coverage, "—");
  });
});

describe("formatDigestTitle", () => {
  it("appends the year when present", () => {
    assert.equal(formatDigestTitle({ title: "Ran", year: 1985 }), "Ran (1985)");
    assert.equal(formatDigestTitle({ title: "Untitled" }), "Untitled");
    assert.equal(formatDigestTitle(null), "");
  });
});

describe("weekly digest theme-safe styles", () => {
  it("defines digest panel styles", () => {
    assert.match(styles, /\.weekly-digest\b/);
    assert.match(styles, /\.weekly-digest-stat\b/);
  });
});
