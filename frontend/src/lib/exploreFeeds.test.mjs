import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMotifQueryParams,
  buildPulseStats,
  normalizeFeed,
  normalizeMotifFacets,
  toggleMotifSelection,
} from "./exploreFeeds.js";

test("normalizeFeed keeps API note and items", () => {
  const result = normalizeFeed({
    feed: "recent-releases",
    items: [{ title: "A" }],
    total: 1,
    note: null,
  });
  assert.equal(result.items.length, 1);
  assert.equal(result.note, null);
  assert.equal(result.meta.feed, "recent-releases");
});

test("normalizeFeed surfaces honest empty notes", () => {
  const result = normalizeFeed({
    items: [],
    note: "No release_date enriched yet.",
  });
  assert.deepEqual(result.items, []);
  assert.equal(result.note, "No release_date enriched yet.");
});

test("normalizeFeed falls back when payload missing", () => {
  const result = normalizeFeed(null, { fallbackNote: "Empty rail." });
  assert.deepEqual(result.items, []);
  assert.equal(result.note, "Empty rail.");
});

test("toggleMotifSelection adds and removes", () => {
  assert.deepEqual(toggleMotifSelection([], "time loop"), ["time loop"]);
  assert.deepEqual(toggleMotifSelection(["time loop", "heist"], "time loop"), ["heist"]);
  assert.deepEqual(toggleMotifSelection(["heist"], "noir"), ["heist", "noir"]);
});

test("buildMotifQueryParams encodes motifs csv", () => {
  const params = buildMotifQueryParams(["time loop", "found family"], { limit: 24 });
  assert.equal(params.get("limit"), "24");
  assert.equal(params.get("motifs"), "time loop,found family");
});

test("buildMotifQueryParams omits motifs when empty", () => {
  const params = buildMotifQueryParams([], { limit: 12 });
  assert.equal(params.get("limit"), "12");
  assert.equal(params.get("motifs"), null);
});

test("buildPulseStats picks editorial overview + health fields", () => {
  const stats = buildPulseStats(
    {
      total: 100,
      movies: 80,
      shows: 20,
      top_genres: [{ genre: "Drama", count: 40 }],
      avg_runtime_minutes: 112.4,
    },
    { unwatched_pct: 33.3, stale_adds: 12 },
  );
  const byId = Object.fromEntries(stats.map((s) => [s.id, s]));
  assert.equal(byId.total.value, "100");
  assert.equal(byId.movies.value, "80");
  assert.equal(byId.unwatched.value, "33%");
  assert.equal(byId.stale.value, "12");
  assert.equal(byId.genre.value, "Drama");
  assert.equal(byId.runtime.value, "112m");
  assert.ok(stats.length <= 7);
});

test("normalizeMotifFacets filters blank values", () => {
  const facets = normalizeMotifFacets({
    facets: [{ value: "heist", count: 3 }, { value: "  ", count: 1 }, { value: "noir", count: 2 }],
  });
  assert.deepEqual(facets, [
    { value: "heist", count: 3 },
    { value: "noir", count: 2 },
  ]);
});
