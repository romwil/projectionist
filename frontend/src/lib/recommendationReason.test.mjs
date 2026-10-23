import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { displayRecommendationReason, posterWhyLine } from "./recommendationReason.js";

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
    assert.equal(displayRecommendationReason("Double feature — first half"), "");
    assert.equal(displayRecommendationReason("Double feature — second half"), "");
    assert.equal(displayRecommendationReason("Unwatched pick for you"), "");
    assert.equal(displayRecommendationReason("Good pick for tonight"), "");
    assert.equal(displayRecommendationReason("Strong plot kinship"), "");
  });
});

describe("posterWhyLine", () => {
  it("shows explanation.sentence only for bridge arrival kinds", () => {
    assert.equal(
      posterWhyLine({
        title: "Contagion",
        explanation: {
          kind: "watched_bridge",
          sentence: "You finished House (2004); Contagion (2011) — both stories turn on a diagnostic puzzle.",
        },
      }),
      "You finished House (2004); Contagion (2011) — both stories turn on a diagnostic puzzle.",
    );
    assert.equal(
      posterWhyLine({
        title: "Peer",
        explanation: { kind: "plot_link", sentence: "Both stories turn on amateur bakers." },
      }),
      "Both stories turn on amateur bakers.",
    );
  });

  it("keeps browse Movies posters why-less even with leftover strings", () => {
    assert.equal(posterWhyLine({ title: "Heat", recommendation_reason: "because you watched Heat" }), "");
    assert.equal(posterWhyLine({ title: "Heat", why: "Strong plot kinship" }), "");
    assert.equal(posterWhyLine({ title: "Heat", explanation: { kind: "", sentence: "because you watched Heat" } }), "");
  });
});
