import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  normalizeFacetHits,
  shouldQueryFacetIndex,
  tagSearchEmptyMessage,
} from "./tagSearch.js";

describe("tagSearch", () => {
  it("normalizes facet payloads", () => {
    assert.deepEqual(
      normalizeFacetHits({
        facets: [
          { value: "found footage", count: 42 },
          { name: "heist", count: "3" },
          { value: "  " },
        ],
      }),
      [
        { value: "found footage", count: 42 },
        { value: "heist", count: 3 },
      ],
    );
  });

  it("requires min chars before querying full index", () => {
    assert.equal(shouldQueryFacetIndex("f"), false);
    assert.equal(shouldQueryFacetIndex("fo"), true);
    assert.equal(shouldQueryFacetIndex("found footage"), true);
  });

  it("builds empty-state copy without chip-only wording", () => {
    const message = tagSearchEmptyMessage("found footage");
    assert.match(message, /No library tags match/);
    assert.doesNotMatch(message, /facet chips/i);
  });
});
