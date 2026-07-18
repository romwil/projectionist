import assert from "node:assert/strict";
import test from "node:test";
import {
  buildMediaBrowseParams,
  libraryExportHref,
  matchesMediaBrowseWatchState,
  mediaBrowseRowsToCsv,
  parseMediaBrowse,
  queryFiltersFromBrowse,
} from "./mediaBrowse.js";

test("parseMediaBrowse keeps supported URL state and bounds limit", () => {
  const state = parseMediaBrowse(new URLSearchParams("view=list&sort=vote_average&sort_dir=desc&limit=1000&genres=Drama,Sci-Fi"));
  assert.equal(state.view, "list");
  assert.equal(state.sort, "vote_average");
  assert.equal(state.sort_dir, "desc");
  assert.equal(state.limit, 100);
  assert.deepEqual(state.genres, ["Drama", "Sci-Fi"]);
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
