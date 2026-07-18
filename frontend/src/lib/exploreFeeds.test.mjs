import assert from "node:assert/strict";
import test from "node:test";

import {
  ADMIN_TASKS_PATH,
  buildMotifQueryParams,
  buildExploreSectionQuery,
  buildPulseStats,
  feedPaginationSummary,
  formatTotalRuntimeMinutes,
  getExploreSectionConfig,
  normalizeFeed,
  normalizeMediaTypeFilter,
  normalizeMotifFacets,
  normalizePageSize,
  ownerEmptyStateCta,
  parseExploreSectionQuery,
  resolveMotifWhy,
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
  const params = buildMotifQueryParams(["time loop", "found family"], { limit: 40 });
  assert.equal(params.get("limit"), "40");
  assert.equal(params.get("motifs"), "time loop,found family");
  assert.equal(params.get("offset"), null);
  assert.equal(params.get("media_type"), null);
  assert.equal(params.get("plot_match_mode"), "hybrid");
});

test("buildMotifQueryParams omits motifs when empty", () => {
  const params = buildMotifQueryParams([], { limit: 20 });
  assert.equal(params.get("limit"), "20");
  assert.equal(params.get("motifs"), null);
  assert.equal(params.get("plot_match_mode"), "hybrid");
});

test("buildMotifQueryParams includes media type and offset", () => {
  const params = buildMotifQueryParams(["heist"], {
    limit: 50,
    offset: 50,
    mediaType: "movie",
  });
  assert.equal(params.get("limit"), "50");
  assert.equal(params.get("offset"), "50");
  assert.equal(params.get("media_type"), "movie");
  assert.equal(params.get("motifs"), "heist");
});

test("buildMotifQueryParams normalizes tv media type and page size", () => {
  const params = buildMotifQueryParams(["comedy"], { limit: 99, mediaType: "tv" });
  assert.equal(params.get("limit"), "20");
  assert.equal(params.get("media_type"), "show");
});

test("buildMotifQueryParams accepts pure motifs mode", () => {
  const params = buildMotifQueryParams(["coma"], { plotMatchMode: "motifs" });
  assert.equal(params.get("plot_match_mode"), "motifs");
});

test("resolveMotifWhy prefers server motif payload", () => {
  const why = resolveMotifWhy(
    {
      matched_motifs: ["extinction", "pennsylvania"],
      motif_why: 'Selected because “extinction” (plot motif + plot text); “pennsylvania” (plot motif).',
      match_layers: [
        { motif: "extinction", layers: ["motif", "plot_text"] },
        { motif: "pennsylvania", layers: ["motif"] },
      ],
      motif_excerpts: [
        { motif: "extinction", excerpt: "…risk of extinction…" },
        { motif: "pennsylvania", excerpt: "…rural Pennsylvania…" },
      ],
    },
    ["extinction", "pennsylvania"],
  );
  assert.equal(why.matched.length, 2);
  assert.match(why.summary, /extinction/);
  assert.equal(why.excerpts[0].motif, "extinction");
  assert.equal(why.matchLayers[0].layers[0], "motif");
});

test("resolveMotifWhy returns null without motif payload", () => {
  assert.equal(resolveMotifWhy({ title: "X" }, ["heist"]), null);
});

test("formatTotalRuntimeMinutes uses days and hours for large totals", () => {
  assert.equal(formatTotalRuntimeMinutes(45), "45m");
  assert.equal(formatTotalRuntimeMinutes(125), "2h 5m");
  assert.equal(formatTotalRuntimeMinutes(1440), "1d");
  assert.equal(formatTotalRuntimeMinutes(1500), "1d 1h");
  assert.equal(formatTotalRuntimeMinutes(0), null);
  assert.equal(formatTotalRuntimeMinutes(null), null);
});

test("buildPulseStats groups Movies/Shows with per-type metrics", () => {
  const stats = buildPulseStats(
    {
      total: 100,
      movies: 80,
      shows: 20,
      by_media_type: {
        movie: {
          count: 80,
          top_genre: { genre: "Drama", count: 30 },
          total_runtime_minutes: 9600,
        },
        show: {
          count: 20,
          top_genre: { genre: "Comedy", count: 8 },
          total_runtime_minutes: 2400,
        },
      },
    },
    {
      unwatched_pct: 33.3,
      stale_adds: 12,
      by_media_type: {
        movie: { total: 80, unwatched_pct: 25, stale_adds: 10 },
        show: { total: 20, unwatched_pct: 50, stale_adds: 2 },
      },
    },
  );
  const byId = Object.fromEntries(stats.map((s) => [s.id, s]));
  assert.equal(byId.total.kind, "summary");
  assert.equal(byId.total.value, "100");
  assert.equal(byId.movies.kind, "media");
  assert.equal(byId.movies.value, "80");
  assert.equal(byId.shows.value, "20");
  const movieMetrics = Object.fromEntries(byId.movies.metrics.map((m) => [m.id, m]));
  assert.equal(movieMetrics.unwatched.value, "25%");
  assert.equal(movieMetrics.stale.value, "10");
  assert.equal(movieMetrics.genre.value, "Drama");
  assert.equal(movieMetrics.runtime.value, "6d 16h");
  const showMetrics = Object.fromEntries(byId.shows.metrics.map((m) => [m.id, m]));
  assert.equal(showMetrics.unwatched.value, "50%");
  assert.equal(showMetrics.genre.value, "Comedy");
  assert.equal(showMetrics.runtime.value, "1d 16h");
  assert.equal(stats.length, 3);
  assert.ok(!byId.unwatched);
  assert.ok(!byId.genre);
});

test("buildPulseStats still returns media cards without by_media_type", () => {
  const stats = buildPulseStats({ total: 5, movies: 3, shows: 2 }, {});
  const byId = Object.fromEntries(stats.map((s) => [s.id, s]));
  assert.equal(byId.movies.value, "3");
  assert.deepEqual(byId.movies.metrics, []);
  assert.equal(byId.shows.value, "2");
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

test("feedPaginationSummary accepts total_matched from library query", () => {
  const summary = feedPaginationSummary({
    total_matched: 90,
    offset: 40,
    limit: 40,
    items: new Array(40).fill({}),
    has_more: true,
  });
  assert.equal(summary.total, 90);
  assert.equal(summary.page, 2);
  assert.equal(summary.pageCount, 3);
  assert.equal(summary.hasMore, true);
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
