import assert from "node:assert/strict";
import test from "node:test";

import { dedupeRecommendations, normalizeRecommendation } from "./recommendationInbox.js";
import { canWatchOnPlex } from "./titleLinks.js";

test("dedupeRecommendations returns the same visible records for a bulk dismissal", () => {
  const visible = dedupeRecommendations([
    { id: "short-note", media_type: "movie", tmdb_id: 78, title: "Blade Runner", message: "Watch this" },
    { id: "other-title", media_type: "movie", tmdb_id: 680, title: "Pulp Fiction" },
    { id: "rich-note", media_type: "movie", tmdb_id: 78, title: "Blade Runner", message: "The final cut is a great rainy-night watch." },
  ]);

  assert.deepEqual(
    visible.map((item) => item.id),
    ["rich-note", "other-title"],
  );
});

test("normalizeRecommendation marks rating-key recommendations as playable library titles", () => {
  assert.equal(
    canWatchOnPlex(normalizeRecommendation({ media_type: "movie", rating_key: "plex-949" })),
    true,
  );
  assert.equal(
    canWatchOnPlex(normalizeRecommendation({ media_type: "movie", rating_key: "plex-949", in_library: false })),
    false,
  );
});
