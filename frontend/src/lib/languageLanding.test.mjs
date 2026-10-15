import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { languageBrowseMeta } from "./titleDetailMeta.js";
import {
  LANGUAGE_MEDIA_TABS,
  NO_MATCHING_TITLES,
  UNKNOWN_LANGUAGE,
  buildLanguageLandingSearch,
  languageLandingPath,
  languageLandingRequest,
} from "./languageLanding.js";

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");

const baseBrowse = {
  view: "poster",
  sort: "title",
  sort_dir: "asc",
  limit: 48,
  offset: 0,
  media_type: "",
  watch_state: "",
  year: "",
  genres: [],
  keywords: [],
};

test("language control links to a relative language landing", () => {
  const meta = languageBrowseMeta("en");
  assert.equal(meta.path, "/explore?language=en");
  assert.equal(languageLandingPath("en"), "/explore?language=en");
  assert.equal(meta.path.includes("automat.vip"), false);
});

test("language landing queries original language for All, Movies, and TV", () => {
  const all = languageLandingRequest("en", baseBrowse);
  assert.equal(all.kind, "query");
  assert.equal(all.filters.original_language, "en");
  assert.equal(all.filters.media_type, undefined);

  const movies = languageLandingRequest("EN", { ...baseBrowse, media_type: "movie" });
  assert.equal(movies.filters.original_language, "en");
  assert.equal(movies.filters.media_type, "movie");

  const tv = languageLandingRequest("en-US", { ...baseBrowse, media_type: "tv" });
  assert.equal(tv.filters.original_language, "en");
  assert.equal(tv.filters.media_type, "show");

  const year = languageLandingRequest("hi", { ...baseBrowse, year: "1999", watch_state: "unwatched" });
  assert.equal(year.filters.original_language, "hi");
  assert.equal(year.filters.year_from, "1999");
  assert.equal(year.filters.year_to, "1999");
  assert.equal(year.filters.year, undefined);
  assert.equal(year.filters.unwatched_only, true);
});

test("empty language does not query and unknown codes do not drop the filter", () => {
  const empty = languageLandingRequest("  ", baseBrowse);
  assert.equal(empty.kind, "empty");
  assert.equal(empty.message, NO_MATCHING_TITLES);
  assert.equal("filters" in empty, false);

  const unknown = languageLandingRequest("notalang", baseBrowse);
  assert.equal(unknown.kind, "unknown");
  assert.equal(unknown.message, UNKNOWN_LANGUAGE);
  assert.equal("filters" in unknown, false);
});

test("toolbar updates keep the relative language param", () => {
  const params = buildLanguageLandingSearch("en", baseBrowse, { media_type: "movie", offset: 0 });
  assert.equal(params.get("language"), "en");
  assert.equal(params.get("media_type"), "movie");
  assert.equal(params.toString().includes("automat.vip"), false);
  const switched = buildLanguageLandingSearch("en", baseBrowse, { language: "ja" });
  assert.equal(switched.get("language"), "ja");
  const cleared = buildLanguageLandingSearch("en", baseBrowse, { language: "" });
  assert.equal(cleared.get("language"), null);
  assert.deepEqual(
    LANGUAGE_MEDIA_TABS.map((tab) => tab.label),
    ["All", "Movies", "TV"],
  );
  assert.equal(LANGUAGE_MEDIA_TABS[0].mediaType, "");
});

test("language landing renders shared browse controls instead of the Explore hub", () => {
  const landing = readFileSync(join(srcDir, "pages", "LanguageLandingPage.jsx"), "utf8");
  const explore = readFileSync(join(srcDir, "pages", "ExplorePage.jsx"), "utf8");
  const detail = readFileSync(join(srcDir, "components", "TitleDetailContent.jsx"), "utf8");

  assert.match(landing, /MediaBrowseControls/);
  assert.match(landing, /MediaBrowsePagination/);
  assert.match(landing, /LANGUAGE_MEDIA_TABS/);
  assert.match(landing, /Select page/);
  assert.match(landing, /Pin \$\{selected\.size \|\| ""\} to watchlist/);
  assert.match(landing, />\s*Delete\s*</);
  assert.match(landing, /request\.kind !== "query"/);
  assert.match(landing, /queryLibrary\(request\.filters\)/);
  assert.match(explore, /searchParams\.has\("language"\)/);
  assert.match(explore, /<LanguageLandingPage \/>/);
  assert.doesNotMatch(explore, /original_language/);
  assert.match(detail, /testId="title-language-link"/);
  assert.match(detail, /to=\{languageMeta\.path\}/);
  assert.doesNotMatch(landing, /automat\.vip/);
});
