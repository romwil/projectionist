import assert from "node:assert/strict";
import test from "node:test";
import {
  MEDIA_BROWSE_ALL_CAP,
  MEDIA_BROWSE_PAGE_SIZES,
  buildMediaBrowseParams,
  isAllPageSize,
  libraryExportHref,
  matchesMediaBrowseWatchState,
  mediaBrowseRowsToCsv,
  parseMediaBrowse,
  queryFiltersFromBrowse,
  resolvePageSizeLimit,
} from "./mediaBrowse.js";

test("parseMediaBrowse keeps supported URL state and caps limit at the ceiling", () => {
  const state = parseMediaBrowse(new URLSearchParams("view=list&sort=vote_average&sort_dir=desc&limit=99999&genres=Drama,Sci-Fi"));
  assert.equal(state.view, "list");
  assert.equal(state.sort, "vote_average");
  assert.equal(state.sort_dir, "desc");
  assert.equal(state.limit, MEDIA_BROWSE_ALL_CAP);
  assert.deepEqual(state.genres, ["Drama", "Sci-Fi"]);
});

test("page-size selector round-trips fixed sizes and the All sentinel", () => {
  assert.deepEqual(MEDIA_BROWSE_PAGE_SIZES, [48, 100, 500, "all"]);

  const fixed = parseMediaBrowse(new URLSearchParams("limit=500"));
  assert.equal(fixed.limit, 500);
  assert.equal(buildMediaBrowseParams(fixed).get("limit"), "500");

  const all = parseMediaBrowse(new URLSearchParams("limit=all"));
  assert.equal(all.limit, "all");
  assert.equal(isAllPageSize(all.limit), true);
  assert.equal(buildMediaBrowseParams(all).get("limit"), "all");

  // Default (48) stays out of the URL to keep links clean.
  const preset = parseMediaBrowse(new URLSearchParams(""));
  assert.equal(preset.limit, 48);
  assert.equal(buildMediaBrowseParams(preset).get("limit"), null);
});

test("resolvePageSizeLimit caps All at the export ceiling and clamps sizes", () => {
  // "All" with a known total returns min(total, cap).
  assert.equal(resolvePageSizeLimit("all", 320), 320);
  assert.equal(resolvePageSizeLimit("all", 99999), MEDIA_BROWSE_ALL_CAP);
  // "All" with unknown total falls back to the cap.
  assert.equal(resolvePageSizeLimit("all"), MEDIA_BROWSE_ALL_CAP);
  // Fixed sizes pass through but never exceed the cap.
  assert.equal(resolvePageSizeLimit(100), 100);
  assert.equal(resolvePageSizeLimit(999999), MEDIA_BROWSE_ALL_CAP);
});

test("queryFiltersFromBrowse resolves the All sentinel to the capped limit", () => {
  const state = parseMediaBrowse(new URLSearchParams("limit=all"));
  assert.equal(queryFiltersFromBrowse(state).limit, MEDIA_BROWSE_ALL_CAP);
});

test("browse query and export preserve current filters", () => {
  const state = parseMediaBrowse(new URLSearchParams("year=1999&watch_state=unwatched&offset=48"));
  assert.deepEqual(queryFiltersFromBrowse(state), {
    sort: "title",
    sort_dir: "asc",
    limit: 48,
    offset: 48,
    unwatched_only: true,
    year: "1999",
  });
  assert.equal(buildMediaBrowseParams(state).get("year"), "1999");
  assert.match(libraryExportHref(state, ["title", "year"]), /columns=title%2Cyear/);
});

test("unwatched excludes watched and in-progress titles", () => {
  assert.equal(matchesMediaBrowseWatchState({ watched: false }, "unwatched"), true);
  assert.equal(matchesMediaBrowseWatchState({ watched: true }, "unwatched"), false);
  assert.equal(matchesMediaBrowseWatchState({ view_offset: 1200 }, "unwatched"), false);
  assert.equal(matchesMediaBrowseWatchState({ view_offset_ms: 1200 }, "unwatched"), false);
});

test("mediaBrowseRowsToCsv serializes visible columns safely", () => {
  assert.equal(
    mediaBrowseRowsToCsv(
      [{ title: 'A "quoted" title', genres: ["Drama", "Sci-Fi"], watched: true }],
      ["title", "genres", "watch_state"],
    ),
    'title,genres,watch_state\n"A ""quoted"" title","Drama · Sci-Fi",Watched',
  );
});
