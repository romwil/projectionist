import assert from "node:assert/strict";
import test from "node:test";

import {
  titleDetailHrefFromTarget,
  titleDetailTargetFromItem,
  titleDetailTargetFromPurgeCandidate,
} from "./titleDetailDrawer.js";

test("titleDetailTargetFromPurgeCandidate prefers tmdb id", () => {
  const candidate = {
    media_type: "movie",
    title: "Mulholland Drive",
    tmdb_id: 1018,
    rating_key: "plex-123",
  };
  assert.deepEqual(titleDetailTargetFromPurgeCandidate(candidate), {
    mediaType: "movie",
    itemId: "1018",
    idType: "tmdb",
  });
});

test("titleDetailTargetFromPurgeCandidate falls back to rating_key", () => {
  const candidate = {
    media_type: "movie",
    title: "Local Only",
    rating_key: "abc/1",
  };
  assert.deepEqual(titleDetailTargetFromPurgeCandidate(candidate), {
    mediaType: "movie",
    itemId: "abc/1",
    idType: "rating_key",
  });
});

test("titleDetailTargetFromItem resolves show tvdb id", () => {
  assert.deepEqual(
    titleDetailTargetFromItem({ media_type: "show", tvdb_id: 12345 }),
    { mediaType: "show", itemId: "12345", idType: "tvdb" },
  );
});

test("titleDetailTargetFromItem returns null when not linkable", () => {
  assert.equal(titleDetailTargetFromItem(null), null);
  assert.equal(titleDetailTargetFromItem({ media_type: "movie", title: "Nope" }), null);
});

test("titleDetailHrefFromTarget builds full-page route", () => {
  assert.equal(
    titleDetailHrefFromTarget({ mediaType: "movie", itemId: "78", idType: "tmdb" }),
    "/title/movie/78",
  );
  assert.equal(
    titleDetailHrefFromTarget({ mediaType: "movie", itemId: "abc/1", idType: "rating_key" }),
    "/title/movie/abc%2F1?id_type=rating_key",
  );
});
