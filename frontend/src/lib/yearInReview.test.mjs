import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  chapterDurationMs,
  nextChapterIndex,
  prevChapterIndex,
  shareCardText,
  shouldAutoAdvance,
  yirPath,
  yirPathFromGenerateResult,
  YIR_DEFAULT_DURATION_MS,
} from "./yearInReview.js";

describe("yearInReview helpers", () => {
  it("uses chapter duration when valid", () => {
    assert.equal(chapterDurationMs([{ duration_ms: 7000 }], 0), 7000);
    assert.equal(chapterDurationMs([{ duration_ms: 500 }], 0), YIR_DEFAULT_DURATION_MS);
  });

  it("advances and retreats chapter indexes safely", () => {
    assert.equal(nextChapterIndex(0, 3), 1);
    assert.equal(nextChapterIndex(2, 3), 2);
    assert.equal(prevChapterIndex(0, 3), 0);
    assert.equal(prevChapterIndex(2, 3), 1);
  });

  it("builds share text and respects pause / reduced motion", () => {
    assert.match(shareCardText({ title: "Hello", body: "World" }, 2025), /2025/);
    assert.equal(shouldAutoAdvance({ paused: false, prefersReducedMotion: false }), true);
    assert.equal(shouldAutoAdvance({ paused: true, prefersReducedMotion: false }), false);
    assert.equal(shouldAutoAdvance({ paused: false, prefersReducedMotion: true }), false);
    assert.equal(yirPath(2024), "/year-in-review/2024");
  });

  it("only links generate results that are ready", () => {
    assert.equal(
      yirPathFromGenerateResult({ year: 2026, status: "ready", path: "/year-in-review/2026" }),
      "/year-in-review/2026",
    );
    assert.equal(yirPathFromGenerateResult({ year: 2026, status: "empty" }), null);
    assert.equal(yirPathFromGenerateResult({ year: 2026, status: "empty", path: null }), null);
    assert.equal(
      yirPathFromGenerateResult({ year: 2026, status: "tease", delivered: 1 }),
      "/year-in-review/2026",
    );
    assert.equal(yirPathFromGenerateResult({ year: 2026 }), null);
  });
});
