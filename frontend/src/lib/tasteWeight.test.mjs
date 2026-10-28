import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { clampTasteWeight, formatTasteWeight } from "./tasteWeight.ts";

describe("tasteWeight", () => {
  it("clamps profile weights onto 0–1", () => {
    assert.equal(clampTasteWeight(0), 0);
    assert.equal(clampTasteWeight(0.85), 0.85);
    assert.equal(clampTasteWeight(1), 1);
    assert.equal(clampTasteWeight(2), 1);
    assert.equal(clampTasteWeight(-0.5), 0);
    assert.equal(clampTasteWeight("nope"), 0);
  });

  it("formats capped percents so 2.0 never renders as 200%", () => {
    assert.equal(formatTasteWeight(0.85), "85%");
    assert.equal(formatTasteWeight(1), "100%");
    assert.equal(formatTasteWeight(2), "100%");
    assert.equal(formatTasteWeight(0), "0%");
    assert.equal(formatTasteWeight(Number.NaN), "—");
  });
});
