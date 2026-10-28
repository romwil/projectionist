import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { languageBrowseMeta } from "./titleDetailMeta.js";
import {
  ALL_LANGUAGES_HEADING,
  ALL_LANGUAGES_LEDE,
  LANGUAGE_LANDING_LEDE,
  buildLanguageLandingSearch,
  languageLandingPath,
  languageLandingRequest,
  languageOptionsFromBuckets,
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

test("blank language lists every title and a code never widens the query", () => {
  const empty = languageLandingRequest("  ", baseBrowse);
  assert.equal(empty.kind, "query");
  assert.equal(empty.code, "");
  assert.equal(empty.filters.original_language, undefined);

  const unknown = languageLandingRequest("notalang", baseBrowse);
  assert.equal(unknown.kind, "query");
  assert.equal(unknown.filters.original_language, "notalang");
});

test("language options are the catalog buckets, not a world list", () => {
  const options = languageOptionsFromBuckets([
    { value: "fr", count: 2 },
    { value: "en", count: 4 },
    { value: "EN", count: 1 },
    { value: "", count: 8 },
    { value: "unknown", count: 3 },
  ]);
  assert.deepEqual(
    options.map((option) => option.code),
    ["en", "fr"],
  );
  assert.equal(options.some((option) => option.code === "ja"), false);
  assert.equal(options.find((option) => option.code === "en")?.label, "English");
  assert.equal(options.find((option) => option.code === "en")?.count, 5);
  assert.equal(options.find((option) => option.code === "fr")?.label, "French");
});

test("toolbar updates keep the relative language param", () => {
  const params = buildLanguageLandingSearch("en", baseBrowse, { media_type: "movie", offset: 0 });
  assert.equal(params.get("language"), "en");
  assert.equal(params.get("media_type"), "movie");
  assert.equal(params.toString().includes("automat.vip"), false);

  const cleared = buildLanguageLandingSearch("en", baseBrowse, { language: "" });
  assert.equal(cleared.get("language"), "");
  assert.equal(cleared.has("language"), true);
});

test("language landing renders shared browse controls instead of the Explore hub", () => {
  const landing = readFileSync(join(srcDir, "pages", "LanguageLandingPage.jsx"), "utf8");
  const explore = readFileSync(join(srcDir, "pages", "ExplorePage.jsx"), "utf8");
  const detail = readFileSync(join(srcDir, "components", "TitleDetailContent.jsx"), "utf8");
  const controls = readFileSync(join(srcDir, "components", "MediaBrowseControls.jsx"), "utf8");

  assert.match(landing, /MediaBrowseControls/);
  assert.match(landing, /MediaBrowsePagination/);
  assert.doesNotMatch(landing, /LANGUAGE_MEDIA_TABS/);
  assert.doesNotMatch(landing, /language-landing-media-tabs/);
  assert.doesNotMatch(landing, /explore-media-tab/);
  assert.match(landing, /getLibraryAggregate\("language"/);
  assert.match(landing, /languageOptionsFromBuckets/);
  assert.equal(ALL_LANGUAGES_HEADING, "All languages");
  assert.equal(LANGUAGE_LANDING_LEDE, "Library titles in this original language");
  assert.equal(ALL_LANGUAGES_LEDE, "Library titles in every original language");
  assert.match(landing, /ALL_LANGUAGES_HEADING/);
  assert.match(landing, /LANGUAGE_LANDING_LEDE/);
  assert.match(landing, /ALL_LANGUAGES_LEDE/);
  assert.match(landing, /Select page/);
  assert.match(landing, /Pin \$\{selected\.size \|\| ""\} to watchlist/);
  assert.match(landing, />\s*Delete\s*</);
  assert.match(landing, /queryLibrary\(request\.filters\)/);
  assert.match(controls, /data-testid="media-browse-language"/);
  assert.match(controls, /<span>Language<\/span>/);
  assert.doesNotMatch(controls, /data-testid="media-browse-language-filter"/);
  assert.match(explore, /searchParams\.has\("language"\)/);
  assert.match(explore, /<LanguageLandingPage \/>/);
  assert.doesNotMatch(explore, /original_language/);
  assert.match(detail, /testId="title-language-link"/);
  assert.match(detail, /to=\{languageMeta\.path\}/);
  assert.doesNotMatch(landing, /automat\.vip/);
});
