import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { libraryBrowsePath } from "./browseLinks.js";
import {
  MEDIA_BROWSE_SORTS,
  MEDIA_BROWSE_TV_SORTS,
  browseTypeChoices,
  parseMediaBrowse,
} from "./mediaBrowse.js";

const page = readFileSync(new URL("../pages/LibraryBrowsePage.jsx", import.meta.url), "utf8");
const controls = readFileSync(
  new URL("../components/MediaBrowseControls.jsx", import.meta.url),
  "utf8",
);
const recentlyAdded = readFileSync(
  new URL("../pages/ExploreSectionPage.jsx", import.meta.url),
  "utf8",
);
const tags = readFileSync(new URL("../pages/TagPage.jsx", import.meta.url), "utf8");

function toolbarBlock(source, testId) {
  const start = source.indexOf(`data-testid="${testId}"`);
  assert.ok(start > 0, `missing ${testId}`);
  const slice = source.slice(start, start + 1800);
  return slice;
}

test("movie and TV landings keep their shelf and a labeled title sort", () => {
  const movies = parseMediaBrowse(new URLSearchParams("media_type=movie"));
  assert.equal(movies.media_type, "movie");
  assert.equal(movies.sort, "title");
  assert.equal(movies.sort_dir, "asc");
  assert.equal(MEDIA_BROWSE_SORTS.find((option) => option.id === "title")?.label, "Title");

  const shows = parseMediaBrowse(new URLSearchParams("media_type=show"));
  assert.equal(shows.media_type, "show");
  assert.equal(shows.sort, "episode_added_at");
  assert.equal(shows.sort_dir, "desc");
  assert.equal(MEDIA_BROWSE_TV_SORTS.find((option) => option.id === "title")?.label, "Title");

  assert.equal(libraryBrowsePath({ mediaType: "movie" }), "/search?media_type=movie");
  assert.match(libraryBrowsePath({ mediaType: "show" }), /media_type=show/);
  assert.deepEqual(browseTypeChoices("movie"), [{ value: "movie", label: "Movies" }]);
  assert.deepEqual(browseTypeChoices("show"), [{ value: "show", label: "TV shows" }]);
  assert.equal(
    browseTypeChoices("").some((choice) => choice.value === ""),
    true,
  );
});

test("movies and TV results render the shared browse controls outside a closed disclosure", () => {
  const toolbar = toolbarBlock(page, "library-browse-toolbar");
  assert.match(toolbar, /<MediaBrowseControls/);
  assert.doesNotMatch(toolbar, /<details/);
  assert.match(toolbar, /filterOptions=\{filterOptions\}/);
  assert.match(toolbar, /pageSizes=\{MEDIA_BROWSE_PAGE_SIZES\}/);
  assert.match(toolbar, /mediaTypeScope=\{landingTypeScope\}/);
  assert.match(toolbar, /MEDIA_BROWSE_TV_SORTS/);
  assert.match(page, /data-testid="library-browse-summary"/);
  assert.match(page, /data-testid="library-browse-select-all"/);
  assert.match(page, /<MediaBrowsePagination/);
  assert.match(page, /getLibraryAggregate\("year", aggregateOptions\)/);
  assert.match(page, /getLibraryAggregate\("genre", aggregateOptions\)/);
  assert.match(controls, /Sort by/);
  assert.match(controls, /Genres/);
  assert.match(controls, /Posters/);
  assert.match(controls, /List/);
  assert.match(controls, /Export CSV/);
  assert.match(controls, /Per page/);
  assert.match(controls, /browseTypeChoices\(mediaTypeScope\)/);
});

test("recently added keeps the same open toolbar and its All / Movies / TV tabs", () => {
  const toolbar = toolbarBlock(recentlyAdded, "explore-section-toolbar");
  assert.match(toolbar, /<MediaBrowseControls/);
  assert.doesNotMatch(toolbar, /<details/);
  assert.match(toolbar, /exportItems/);
  assert.match(toolbar, /pageSizes=\{EXPLORE_PAGE_SIZES\}/);
  assert.match(recentlyAdded, /data-testid="explore-section-media-tabs"/);
  assert.doesNotMatch(recentlyAdded, /mediaTypeScope/);
});

test("tag results use the same browse controls, including year, genres, page size, and pagination", () => {
  const toolbar = toolbarBlock(tags, "tag-browse-toolbar");
  assert.match(toolbar, /<MediaBrowseControls/);
  assert.match(toolbar, /filterOptions=\{filterOptions\}/);
  assert.match(toolbar, /pageSizes=\{MEDIA_BROWSE_PAGE_SIZES\}/);
  assert.match(tags, /<MediaBrowsePagination/);
  assert.doesNotMatch(toolbar, /<details/);
});
