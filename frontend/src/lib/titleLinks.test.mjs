import assert from "node:assert/strict";
import test from "node:test";

import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "./titleLinks.js";

test("titleDetailPath prefers tmdb id", () => {
  assert.equal(
    titleDetailPath({ media_type: "movie", tmdb_id: 78, rating_key: "123" }),
    "/title/movie/78",
  );
  assert.equal(
    titleDetailPath({ media_type: "show", tmdb_id: 1396 }),
    "/title/show/1396",
  );
});

test("titleDetailPath falls back to rating_key then tvdb", () => {
  assert.equal(
    titleDetailPath({ media_type: "movie", rating_key: "abc/1" }),
    "/title/movie/abc%2F1?id_type=rating_key",
  );
  assert.equal(
    titleDetailPath({ media_type: "movie", plex_rating_key: "plex-9" }),
    "/title/movie/plex-9?id_type=rating_key",
  );
  assert.equal(
    titleDetailPath({ media_type: "show", tvdb_id: 12345 }),
    "/title/show/12345?id_type=tvdb",
  );
  assert.equal(titleDetailPath({ media_type: "movie", title: "Nope" }), null);
});

test("plexWatchUrl requires rating key and machine id", () => {
  assert.equal(plexWatchUrl("", "server-1"), "");
  assert.equal(plexWatchUrl("99", ""), "");
  assert.equal(
    plexWatchUrl("99", "machine-abc"),
    "https://app.plex.tv/desktop/#!/server/machine-abc/details?key=%2Flibrary%2Fmetadata%2F99",
  );
});

test("canWatchOnPlex only when in library with rating_key", () => {
  assert.equal(canWatchOnPlex({ in_library: true, rating_key: "1" }), true);
  assert.equal(canWatchOnPlex({ in_library: false, rating_key: "1" }), false);
  assert.equal(canWatchOnPlex({ in_library: true, rating_key: "" }), false);
  assert.equal(canWatchOnPlex({ in_library: true }), false);
});
