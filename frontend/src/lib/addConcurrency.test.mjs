import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  addItemKey,
  isAddBlockedForKey,
  withAddInFlight,
  withoutAddInFlight,
} from "./addConcurrency.js";

describe("add concurrency", () => {
  it("builds distinct keys per card/target", () => {
    const a = addItemKey({ media_type: "movie", tmdb_id: 1, title: "A" }, "radarr");
    const b = addItemKey({ media_type: "movie", tmdb_id: 2, title: "B" }, "radarr");
    assert.notEqual(a, b);
  });

  it("only blocks the in-flight key", () => {
    const keyA = addItemKey({ media_type: "movie", tmdb_id: 1, title: "A" }, "radarr");
    const keyB = addItemKey({ media_type: "movie", tmdb_id: 2, title: "B" }, "radarr");
    const inFlight = withAddInFlight(new Set(), keyA);
    assert.equal(isAddBlockedForKey(inFlight, keyA), true);
    assert.equal(isAddBlockedForKey(inFlight, keyB), false);
    assert.equal(isAddBlockedForKey(withoutAddInFlight(inFlight, keyA), keyA), false);
  });
});
