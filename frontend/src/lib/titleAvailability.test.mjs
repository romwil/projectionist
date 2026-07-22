import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  titleAvailability,
  titleAvailabilityClassName,
} from "./titleAvailability.js";

describe("titleAvailability", () => {
  it("reports in-library first", () => {
    const result = titleAvailability(
      { in_library: true, tmdb_id: 1, media_type: "movie" },
      { requestPath: "seerr" },
    );
    assert.equal(result.status, "in_library");
    assert.match(result.label, /In your library/);
    assert.equal(result.shortLabel, "In library");
  });

  it("marks Seerr-path titles requestable when not in library", () => {
    const result = titleAvailability(
      { in_library: false, tmdb_id: 42, media_type: "movie" },
      { requestPath: "seerr" },
    );
    assert.equal(result.status, "requestable");
    assert.equal(result.label, "Requestable");
  });

  it("treats seerrEnabled as requestable even when requestPath is arr", () => {
    const result = titleAvailability(
      { tmdb_id: 7, media_type: "show" },
      { requestPath: "arr", seerrEnabled: true },
    );
    assert.equal(result.status, "requestable");
  });

  it("says not here yet when Seerr is off", () => {
    const result = titleAvailability(
      { tmdb_id: 9, media_type: "movie" },
      { requestPath: "arr" },
    );
    assert.equal(result.status, "not_here");
    assert.equal(result.label, "Not here yet");
  });

  it("says not here yet without a TMDB id even on Seerr path", () => {
    const result = titleAvailability(
      { media_type: "movie" },
      { requestPath: "seerr" },
    );
    assert.equal(result.status, "not_here");
  });
});

describe("titleAvailabilityClassName", () => {
  it("maps statuses to CSS modifiers", () => {
    assert.equal(titleAvailabilityClassName("in_library"), "title-availability--in-library");
    assert.equal(titleAvailabilityClassName("requestable"), "title-availability--requestable");
    assert.equal(titleAvailabilityClassName("not_here"), "title-availability--not-here");
  });
});
