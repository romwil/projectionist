import assert from "node:assert/strict";
import test from "node:test";

import {
  SURPRISE_SECTION_INTRO,
  buildSurpriseWhy,
  genreContrast,
  metadataOverlapFromScores,
  visibleSurpriseItems,
} from "./surpriseNeighbors.js";

test("SURPRISE_SECTION_INTRO frames the section", () => {
  assert.match(SURPRISE_SECTION_INTRO, /share DNA/i);
  assert.match(SURPRISE_SECTION_INTRO, /shelf/i);
});

test("metadataOverlapFromScores inverts surprise = cosine × (1 − overlap)", () => {
  assert.ok(Math.abs(metadataOverlapFromScores(0.9, 0.72) - 0.2) < 1e-9);
  assert.equal(metadataOverlapFromScores(0.8, 0.8), 0);
  assert.equal(metadataOverlapFromScores(0, 0.5), null);
  assert.equal(metadataOverlapFromScores(null, 0.5), null);
});

test("genreContrast reports shared and divergent labels", () => {
  const contrast = genreContrast(["Sci-Fi", "Thriller"], ["Romance", "Thriller"]);
  assert.deepEqual(contrast.shared, ["Thriller"]);
  assert.deepEqual(contrast.seedOnly, ["Sci-Fi"]);
  assert.deepEqual(contrast.neighborOnly, ["Romance"]);
});

test("buildSurpriseWhy explains high cosine + low overlap", () => {
  const why = buildSurpriseWhy(
    {
      score: 0.9,
      surprise_score: 0.81,
      genres: ["Romance", "Drama"],
    },
    { seedGenres: ["Sci-Fi", "Action"] },
  );
  assert.ok(why);
  assert.match(why.headline, /different shelf|unexpected|Surprising/i);
  assert.match(why.detail, /plot/i);
  assert.match(why.detail, /overlap|shelf|Genres|Different/i);
  assert.ok(why.signals.some((s) => /Romance|Drama/.test(s)));
});

test("buildSurpriseWhy prefers API metadata_overlap when present", () => {
  const why = buildSurpriseWhy({
    score: 0.9,
    surprise_score: 0.1,
    metadata_overlap: 0.12,
    genres: ["Noir"],
  });
  assert.ok(why);
  assert.match(why.detail, /Almost no shared|barely overlap/i);
});

test("buildSurpriseWhy returns null without signals", () => {
  assert.equal(buildSurpriseWhy({ title: "X" }), null);
  assert.equal(buildSurpriseWhy(null), null);
});

test("visibleSurpriseItems caps until expanded", () => {
  const items = Array.from({ length: 10 }, (_, i) => ({ id: i }));
  assert.equal(visibleSurpriseItems(items, { expanded: false, initial: 6 }).length, 6);
  assert.equal(visibleSurpriseItems(items, { expanded: true, initial: 6 }).length, 10);
  assert.equal(visibleSurpriseItems(items.slice(0, 3), { expanded: false }).length, 3);
});
