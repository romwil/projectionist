import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildAndTagPath,
  moveTypeaheadIndex,
  normalizeFacetHits,
  normalizeTagSort,
  parseAndTags,
  shouldQueryFacetIndex,
  tagSearchEmptyMessage,
  toggleTagSelection,
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

  it("moves typeahead highlight with keyboard", () => {
    assert.equal(moveTypeaheadIndex(-1, "ArrowDown", 3), 0);
    assert.equal(moveTypeaheadIndex(0, "ArrowDown", 3), 1);
    assert.equal(moveTypeaheadIndex(2, "ArrowUp", 3), 1);
  });

  it("builds AND tag paths and parses and= params", () => {
    const path = buildAndTagPath((name) => `/tag/${encodeURIComponent(name)}`, [
      "heist",
      "noir",
    ]);
    assert.equal(path, "/tag/heist?and=noir");
    assert.deepEqual(parseAndTags(new URLSearchParams("and=noir,time loop")), [
      "noir",
      "time loop",
    ]);
    assert.equal(normalizeTagSort("added_at"), "added_at");
    assert.deepEqual(toggleTagSelection(["heist"], "noir"), ["heist", "noir"]);
  });
});
