import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  decadeYearRange,
  exploreCastPath,
  exploreCountryPath,
  exploreDecadePath,
  exploreDirectorsPath,
  exploreGenrePath,
  exploreLanguagePath,
  exploreSectionPath,
  libraryBrowsePath,
  personPath,
  tagPath,
} from "./browseLinks.js";

describe("browseLinks", () => {
  it("builds person paths from numeric ids", () => {
    assert.equal(personPath(287), "/person/287");
    assert.equal(personPath("31"), "/person/31");
    assert.equal(personPath(null), null);
    assert.equal(personPath(""), null);
  });

  it("builds encoded tag and explore deep-links", () => {
    assert.equal(tagPath("time travel"), "/tag/time%20travel");
    assert.equal(exploreGenrePath("Sci-Fi"), "/explore?genre=Sci-Fi");
    assert.equal(exploreCastPath("Keanu Reeves"), "/explore?cast=Keanu%20Reeves");
    assert.equal(exploreDirectorsPath("Lana Wachowski"), "/explore?directors=Lana%20Wachowski");
    assert.equal(exploreDecadePath("2020s"), "/explore?decade=2020s");
    assert.equal(exploreLanguagePath("hi"), "/explore?language=hi");
    assert.equal(exploreCountryPath("India"), "/explore?country=India");
    assert.deepEqual(decadeYearRange("1970s"), { year_from: 1970, year_to: 1979 });
    assert.equal(
      exploreSectionPath("recently-added", { mediaType: "movie" }),
      "/explore/section/recently-added?media_type=movie",
    );
    assert.equal(exploreSectionPath("recent-releases"), "/explore/section/recent-releases");
  });

  it("builds unified library browse deep-links", () => {
    assert.equal(libraryBrowsePath(), "/explore/browse");
    assert.equal(libraryBrowsePath({ mediaType: "movie" }), "/explore/browse?media_type=movie");
    assert.equal(libraryBrowsePath({ mediaType: "show" }), "/explore/browse?media_type=show");
    // Unknown media types are dropped rather than forwarded.
    assert.equal(libraryBrowsePath({ mediaType: "episode" }), "/explore/browse");
    assert.equal(libraryBrowsePath({ q: "blade runner" }), "/explore/browse?q=blade+runner");
    assert.equal(
      libraryBrowsePath({ mediaType: "movie", q: "noir" }),
      "/explore/browse?media_type=movie&q=noir",
    );
  });
});
