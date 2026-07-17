import assert from "node:assert/strict";
import test from "node:test";

import {
  ADMIN_TASKS_PATH,
  buildMotifQueryParams,
  buildExploreSectionQuery,
  buildPulseStats,
  feedPaginationSummary,
  getExploreSectionConfig,
  normalizeFeed,
  normalizeMediaTypeFilter,
  normalizeMotifFacets,
  normalizePageSize,
  ownerEmptyStateCta,
  parseExploreSectionQuery,
  sortExploreSectionItems,
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

test("parseExploreSectionQuery normalizes pagination and media type", () => {
  const params = new URLSearchParams("media_type=tv&limit=40&offset=20");
  assert.deepEqual(parseExploreSectionQuery(params), {
    limit: 40,
    offset: 20,
    mediaType: "show",
    sort: "default",
  });
  assert.equal(normalizePageSize("99"), 20);
  assert.equal(normalizeMediaTypeFilter("movies"), "movie");
});

test("buildExploreSectionQuery omits default limit and zero offset", () => {
  const params = buildExploreSectionQuery(
    { limit: 40, offset: 20, mediaType: "movie" },
    { offset: 0 },
  );
  assert.equal(params.get("media_type"), "movie");
  assert.equal(params.get("limit"), "40");
  assert.equal(params.get("offset"), null);
});

test("sortExploreSectionItems sorts by year desc", () => {
  const sorted = sortExploreSectionItems(
    [
      { title: "B", year: 1990 },
      { title: "A", year: 2000 },
      { title: "C", year: null },
    ],
    "year",
  );
  assert.deepEqual(
    sorted.map((item) => item.title),
    ["A", "B", "C"],
  );
});

test("feedPaginationSummary computes page metadata", () => {
  const summary = feedPaginationSummary({
    total: 45,
    offset: 20,
    limit: 20,
    items: new Array(20).fill({}),
    has_more: true,
  });
  assert.equal(summary.page, 2);
  assert.equal(summary.pageCount, 3);
  assert.equal(summary.hasMore, true);
  assert.equal(summary.hasPrev, true);
});

test("getExploreSectionConfig resolves known sections", () => {
  const config = getExploreSectionConfig("recent-releases");
  assert.equal(config?.feed, "recent-releases");
  assert.equal(getExploreSectionConfig("unknown"), null);
});

test("ownerEmptyStateCta deep-links owners to Scheduled Tasks for cold caches", () => {
  assert.equal(ownerEmptyStateCta("Empty — plot_neighbors cache not built yet for this title."), null);
  assert.deepEqual(
    ownerEmptyStateCta("Empty — plot_neighbors cache not built yet for this title.", {
      isOwner: true,
    }),
    { label: "Warm Explore", href: ADMIN_TASKS_PATH },
  );
  assert.deepEqual(
    ownerEmptyStateCta(
      "No release_date/first_air_date enriched yet — run library sync or metadata_enrichment.",
      { isOwner: true },
    ),
    { label: "Run enrichment", href: ADMIN_TASKS_PATH },
  );
  assert.deepEqual(
    ownerEmptyStateCta(
      "No plot motifs yet — summary_motifs idle task has not populated facets.",
      { isOwner: true },
    ),
    { label: "Run enrichment", href: ADMIN_TASKS_PATH },
  );
  assert.equal(
    ownerEmptyStateCta("No titles match the selected motifs.", { isOwner: true }),
    null,
  );
});
