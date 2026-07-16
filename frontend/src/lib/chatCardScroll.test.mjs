import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  INLINE_CARDS_MAX_HEIGHT_VH,
  REVIEW_BATCH_MAX_HEIGHT_VH,
  scrollableCardStripStyle,
} from "./chatCardScroll.js";

describe("scrollableCardStripStyle", () => {
  it("returns contained overflow styles with default max height", () => {
    const style = scrollableCardStripStyle();
    assert.equal(style.maxHeight, `${INLINE_CARDS_MAX_HEIGHT_VH}vh`);
    assert.equal(style.overflowY, "auto");
    assert.equal(style.overflowX, "auto");
  });

  it("clamps extreme values", () => {
    assert.equal(scrollableCardStripStyle(5).maxHeight, "12vh");
    assert.equal(scrollableCardStripStyle(200).maxHeight, "80vh");
  });

  it("exposes review-batch constant in a sensible range", () => {
    assert.ok(REVIEW_BATCH_MAX_HEIGHT_VH >= 20);
    assert.ok(REVIEW_BATCH_MAX_HEIGHT_VH <= INLINE_CARDS_MAX_HEIGHT_VH);
  });
});
