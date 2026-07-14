import test from "node:test";
import assert from "node:assert/strict";
import { allowWatchlistPin } from "./watchlistPin.js";

test("allowWatchlistPin rejects purge cards", () => {
  assert.equal(allowWatchlistPin({ card_kind: "purge", title: "X" }), false);
  assert.equal(allowWatchlistPin({ purge_candidate: true }), false);
});

test("allowWatchlistPin allows recommendation cards", () => {
  assert.equal(allowWatchlistPin({ title: "Inception", tmdb_id: 27205 }), true);
  assert.equal(allowWatchlistPin({ card_kind: "recommendation" }), true);
});
