import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { displayRecommendationReason } from "./recommendationReason.js";

describe("displayRecommendationReason", () => {
  it("keeps human curator rationale", () => {
    assert.equal(
      displayRecommendationReason("British Quatermass energy, like The Earth Dies Screaming"),
      "British Quatermass energy, like The Earth Dies Screaming",
    );
  });

  it("drops empty and pipeline labels", () => {
    assert.equal(displayRecommendationReason(""), "");
    assert.equal(displayRecommendationReason(null), "");
    assert.equal(displayRecommendationReason("TMDB title match"), "");
    assert.equal(displayRecommendationReason("TMDb title match"), "");
    assert.equal(displayRecommendationReason("tmdb search"), "");
    assert.equal(displayRecommendationReason("Missing from your collection"), "");
  });
});
