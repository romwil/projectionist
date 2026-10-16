import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { libraryBrowsePath } from "./browseLinks.js";
import {
  MEDIA_BROWSE_SORTS,
  MEDIA_BROWSE_TV_SORTS,
  browseFacetsFollowGrid,
  browseTypeChoices,
  isMovieBrowseLanding,
  movieLandingBrowseDefaults,
  parseMediaBrowse,
  queryFiltersFromBrowse,
} from "./mediaBrowse.js";
import { browseLanguageOptions } from "./languageNames.js";

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
  const movieParams = new URLSearchParams("media_type=movie");
  assert.equal(isMovieBrowseLanding("/search", movieParams), true);
  const movies = parseMediaBrowse(movieParams, movieLandingBrowseDefaults());
  assert.equal(movies.media_type, "movie");
  assert.equal(movies.sort, "added_at");
  assert.equal(movies.sort_dir, "desc");
  assert.equal(MEDIA_BROWSE_SORTS.find((option) => option.id === "added_at")?.label, "Date added");
  const movieFilters = queryFiltersFromBrowse(movies);
  assert.equal(movieFilters.sort, "added_at");
  assert.equal(movieFilters.sort_dir, "desc");
  assert.equal(movieFilters.limit, 48);
  assert.equal(movieFilters.offset, 0);

  const titled = parseMediaBrowse(
    new URLSearchParams("media_type=movie&sort=title&sort_dir=asc"),
    movieLandingBrowseDefaults(),
  );
  assert.equal(titled.sort, "title");
  assert.equal(titled.sort_dir, "asc");

  const unscoped = queryFiltersFromBrowse(parseMediaBrowse(new URLSearchParams("")));
  assert.equal(unscoped.sort, "title");
  assert.equal(unscoped.sort_dir, "asc");
  assert.equal(isMovieBrowseLanding("/search", new URLSearchParams("")), false);
  assert.equal(isMovieBrowseLanding("/tags/drama", movieParams), false);

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
  assert.match(page, /getLibraryAggregate\("language", aggregateOptions\)/);
  assert.match(page, /topExamples: 0/);
  assert.match(page, /browseFacetsFollowGrid\(gridSettled\)/);
  assert.equal(browseFacetsFollowGrid(false), false);
  assert.equal(browseFacetsFollowGrid(true), true);
  const facetEffect = page.slice(page.indexOf("browseFacetsFollowGrid"));
  const queryAt = page.indexOf("queryLibrary(filters)");
  const facetAt = page.indexOf("browseFacetsFollowGrid(gridSettled)");
  assert.ok(queryAt > 0 && facetAt > 0);
  assert.match(facetEffect, /if \(!browseFacetsFollowGrid\(gridSettled\)/);
  assert.match(controls, /Sort by/);
  assert.match(controls, /Genres/);
  assert.match(controls, /Posters/);
  assert.match(controls, /List/);
  assert.match(controls, /Export CSV/);
  assert.match(controls, /Per page/);
  assert.match(controls, /browseTypeChoices\(mediaTypeScope\)/);
});

test("movies browse bar filters the library query by original language", () => {
  const yearAt = controls.indexOf("<span>Year</span>");
  const languageAt = controls.indexOf('data-testid="media-browse-language"');
  const genresAt = controls.indexOf("<span>Genres</span>");
  assert.ok(yearAt > 0 && languageAt > yearAt && genresAt > languageAt);
  assert.match(controls, /<span>Language<\/span>/);
  assert.match(controls, /<option value="">Any<\/option>/);
  assert.match(page, /getLibraryAggregate\("language", aggregateOptions\)/);
  assert.match(page, /queryLibrary\(filters\)/);
  const withLanguage = queryFiltersFromBrowse(
    parseMediaBrowse(
      new URLSearchParams("media_type=movie&language=ja&offset=48"),
      movieLandingBrowseDefaults(),
    ),
  );
  assert.equal(withLanguage.sort, "added_at");
  assert.equal(withLanguage.sort_dir, "desc");
  assert.equal(withLanguage.original_language, "ja");
  assert.equal(withLanguage.offset, 48);

  const state = parseMediaBrowse(
    new URLSearchParams("media_type=movie&language=en&year=2016&watch_state=unwatched&genres=Drama"),
  );
  const filters = queryFiltersFromBrowse(state);
  assert.equal(filters.media_type, "movie");
  assert.equal(filters.original_language, "en");
  assert.equal(filters.language, undefined);
  assert.equal(filters.year, "2016");
  assert.equal(filters.unwatched_only, true);
  assert.deepEqual(filters.genres, ["Drama"]);

  const unknown = queryFiltersFromBrowse(
    parseMediaBrowse(new URLSearchParams("media_type=movie&language=notalang")),
  );
  assert.equal(unknown.media_type, "movie");
  assert.equal(unknown.original_language, "notalang");

  assert.deepEqual(browseLanguageOptions(["en", "ja", "en-US", "notalang", ""]), [
    { code: "en", label: "English" },
    { code: "ja", label: "Japanese" },
  ]);
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
