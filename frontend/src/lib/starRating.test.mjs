import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clampStars,
  formatStarsLabel,
  starFillForValue,
  starValueFromKey,
  starValueFromPointerX,
} from "./starRating.js";

describe("starRating", () => {
  it("clamps and snaps to half-star steps", () => {
    assert.equal(clampStars(4.5), 4.5);
    assert.equal(clampStars(4.4), 4.5);
    assert.equal(clampStars(0), 0);
    assert.equal(clampStars(5.2), 5);
    assert.equal(clampStars(0.25), 0.5);
  });

  it("formats labels and fill states", () => {
    assert.equal(formatStarsLabel(4), "4");
    assert.equal(formatStarsLabel(4.5), "4.5");
    assert.equal(starFillForValue(3.5, 3), "full");
    assert.equal(starFillForValue(3.5, 4), "half");
    assert.equal(starFillForValue(3.5, 5), "empty");
  });

  it("steps with arrow keys including half increments", () => {
    assert.equal(starValueFromKey("ArrowRight", 0), 0.5);
    assert.equal(starValueFromKey("ArrowRight", 0.5), 1);
    assert.equal(starValueFromKey("ArrowLeft", 1), 0.5);
    assert.equal(starValueFromKey("ArrowLeft", 0.5), 0);
    assert.equal(starValueFromKey("Home", 3), 0.5);
    assert.equal(starValueFromKey("End", 1), 5);
    assert.equal(starValueFromKey("a", 2), null);
  });

  it("maps pointer X to left/right half of a star", () => {
    const el = {
      getBoundingClientRect: () => ({ left: 100, width: 40 }),
    };
    assert.equal(starValueFromPointerX(110, el, 3), 2.5);
    assert.equal(starValueFromPointerX(130, el, 3), 3);
  });
});
