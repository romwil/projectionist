import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizeTonightItems, tonightStripVisible } from "./tonightStrip.js";

describe("tonightStrip", () => {
  it("normalizes and dedupes items to max 3", () => {
    const items = normalizeTonightItems({
      items: [
        { title: "A", media_type: "movie", tmdb_id: 1 },
        { title: "A", media_type: "movie", tmdb_id: 1 },
        { title: "B", media_type: "movie", tmdb_id: 2 },
        { title: "C", media_type: "show", tmdb_id: 3 },
        { title: "D", media_type: "movie", tmdb_id: 4 },
      ],
    });
    assert.equal(items.length, 3);
    assert.equal(items[0].title, "A");
  });

  it("visibility respects dismiss and loading", () => {
    assert.equal(tonightStripVisible([], { loading: true }), true);
    assert.equal(tonightStripVisible([{ title: "A" }], { dismissed: true }), false);
    assert.equal(tonightStripVisible([{ title: "A" }]), true);
  });
});
