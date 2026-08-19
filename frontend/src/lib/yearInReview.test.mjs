import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  chapterDurationMs,
  monthBarPercents,
  nextChapterIndex,
  prevChapterIndex,
  recapIsReady,
  recapShareText,
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

  it("builds recap share text and month bar percents", () => {
    const recap = {
      headline: "Horror movies. Drama TV. That was your year.",
      hero: [{ value: "47", label: "movies finished" }],
      movie_genre: { name: "Horror" },
      tv_genre: { name: "Drama" },
      monthly_counts: { 6: 10, 7: 5 },
    };
    const text = recapShareText(recap, 2026);
    assert.match(text, /Horror movies/);
    assert.match(text, /47 movies finished/);
    assert.match(text, /Movies: Horror/);
    const bars = monthBarPercents(recap.monthly_counts);
    assert.equal(bars.length, 12);
    assert.equal(bars[5], 1);
    assert.equal(bars[6], 0.5);
    assert.equal(recapIsReady({ status: "ready", recap }), true);
    assert.equal(recapIsReady({ status: "tease", recap }), false);
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
