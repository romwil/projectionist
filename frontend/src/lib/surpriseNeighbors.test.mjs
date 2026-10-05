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
  assert.match(SURPRISE_SECTION_INTRO, /story/i);
  assert.match(SURPRISE_SECTION_INTRO, /shelf/i);
  assert.match(SURPRISE_SECTION_INTRO, /plots share/i);
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

test("buildSurpriseWhy explains a named kinship and keeps low overlap second", () => {
  const why = buildSurpriseWhy(
    {
      score: 0.9,
      surprise_score: 0.81,
      plot_link: "Both stories turn on amateur bakers and a signature bake.",
      genres: ["Romance", "Drama"],
    },
    { seedGenres: ["Sci-Fi", "Action"] },
  );
  assert.ok(why);
  assert.match(why.headline, /amateur bakers/i);
  assert.match(why.detail, /^Both stories turn on/i);
  assert.match(why.detail, /barely overlap/i);
  assert.doesNotMatch(why.detail, /^Almost no shared|^Shelf labels/i);
  assert.ok(why.signals.some((s) => /Romance|Drama|Different shelf/.test(s)));
});

test("buildSurpriseWhy excludes a neighbor whose only signal is missing labels", () => {
  assert.equal(
    buildSurpriseWhy({
      score: 0.9,
      surprise_score: 0.9,
      metadata_overlap: 0,
      genres: ["Noir"],
    }),
    null,
  );
  assert.equal(
    buildSurpriseWhy({
      score: 0.9,
      surprise_score: 0.1,
      metadata_overlap: 0.12,
      plot_link: "Almost no shared genre, keyword, or credit labels",
      genres: ["Noir"],
    }),
    null,
  );
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
