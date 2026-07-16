import assert from "node:assert/strict";
import test from "node:test";

import { formatMatchPercent } from "./matchScore.js";

test("formatMatchPercent returns empty for missing scores", () => {
  assert.equal(formatMatchPercent(null), "");
  assert.equal(formatMatchPercent({}), "");
  assert.equal(formatMatchPercent({ score: "nope" }), "");
});

test("formatMatchPercent accepts 0–1 fractions", () => {
  assert.equal(formatMatchPercent({ score: 0.87 }), "87% Match");
  assert.equal(formatMatchPercent({ match_score: 0.984 }), "98% Match");
});

test("formatMatchPercent accepts 0–100 percentages", () => {
  assert.equal(formatMatchPercent({ match_pct: 72 }), "72% Match");
  assert.equal(formatMatchPercent({ taste_match: 91.4 }), "91% Match");
});

test("formatMatchPercent prefers match_pct over score", () => {
  assert.equal(formatMatchPercent({ match_pct: 80, score: 0.1 }), "80% Match");
});

test("formatMatchPercent ignores zero and out-of-range", () => {
  assert.equal(formatMatchPercent({ score: 0 }), "");
  assert.equal(formatMatchPercent({ score: -1 }), "");
  assert.equal(formatMatchPercent({ score: 150 }), "");
});
