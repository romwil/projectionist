import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  chapterDurationMs,
  monthBarPercents,
  nextChapterIndex,
  posterPreviewCount,
  prevChapterIndex,
  recapIsReady,
  recapShareText,
  runConfirmedYirGenerate,
  shareCardText,
  shouldAutoAdvance,
  visiblePosters,
  yirPath,
  yirPathFromGenerateResult,
  YIR_BINGE_POSTER_PREVIEW_DEFAULT,
  YIR_DEFAULT_DURATION_MS,
  YIR_POSTER_PREVIEW_DEFAULT,
  YIR_SELF_GENERATE_PAYLOAD,
} from "./yearInReview.ts";

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

  it("expands poster strips beyond the preview count", () => {
    assert.equal(posterPreviewCount({ kind: "tv_depth" }), YIR_BINGE_POSTER_PREVIEW_DEFAULT);
    assert.equal(posterPreviewCount({ posters_preview: 8 }), 8);
    assert.equal(posterPreviewCount({ kind: "top_movies" }), YIR_POSTER_PREVIEW_DEFAULT);
    const posters = Array.from({ length: 7 }, (_, i) => ({ title: `T${i}` }));
    assert.equal(visiblePosters(posters, 4, false).length, 4);
    assert.equal(visiblePosters(posters, 4, true).length, 7);
    assert.equal(visiblePosters(posters, 6, false).length, 6);
  });

  it("runs generateYearInReview only after confirm", async () => {
    const calls = [];
    const generate = async (payload) => {
      calls.push(payload);
      return { ok: true };
    };
    assert.equal(await runConfirmedYirGenerate({ confirmed: false, generate }), null);
    assert.deepEqual(calls, []);
    const snap = await runConfirmedYirGenerate({ confirmed: true, generate });
    assert.deepEqual(calls, [YIR_SELF_GENERATE_PAYLOAD]);
    assert.deepEqual(snap, { ok: true });
  });
});
