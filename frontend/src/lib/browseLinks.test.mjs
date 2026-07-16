import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  exploreCastPath,
  exploreDirectorsPath,
  exploreGenrePath,
  exploreSectionPath,
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
    assert.equal(
      exploreSectionPath("recently-added", { mediaType: "movie" }),
      "/explore/section/recently-added?media_type=movie",
    );
    assert.equal(exploreSectionPath("recent-releases"), "/explore/section/recent-releases");
  });
});
