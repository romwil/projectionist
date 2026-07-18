import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPlotKnowledgePanel,
  formatMatchLayerLabel,
  formatMatchLayers,
} from "./plotKnowledge.js";

test("formatMatchLayerLabel maps known layers", () => {
  assert.equal(formatMatchLayerLabel("motif"), "Motif");
  assert.equal(formatMatchLayerLabel("keyword"), "Keyword");
  assert.equal(formatMatchLayerLabel("plot_text"), "Plot text");
  assert.equal(formatMatchLayerLabel("theme"), "Theme");
  assert.equal(formatMatchLayerLabel("custom_layer"), "custom layer");
});

test("formatMatchLayers joins labels", () => {
  assert.equal(formatMatchLayers(["motif", "plot_text"]), "Motif + Plot text");
  assert.equal(formatMatchLayers([]), "");
});

test("buildPlotKnowledgePanel returns null outside library", () => {
  assert.equal(buildPlotKnowledgePanel({ title: "X", in_library: false }), null);
  assert.equal(buildPlotKnowledgePanel(null), null);
});

test("buildPlotKnowledgePanel surfaces layers chips and neighbor count", () => {
  const panel = buildPlotKnowledgePanel({
    in_library: true,
    overview: "A plot.",
    keywords: ["revenge", "martial arts"],
    plot_knowledge: {
      has_overview: true,
      has_tagline: true,
      has_logline: false,
      synopsis_supported: false,
      motifs: ["bride", "coma"],
      themes: [],
      neighbor_count: 12,
    },
  });
  assert.equal(panel.empty, false);
  assert.deepEqual(
    panel.layers.filter((l) => l.present).map((l) => l.id),
    ["overview", "tagline"],
  );
  assert.ok(!panel.layers.some((l) => l.id === "synopsis"));
  assert.deepEqual(panel.motifs, ["bride", "coma"]);
  assert.deepEqual(panel.keywords, ["revenge", "martial arts"]);
  assert.equal(panel.neighborCount, 12);
});

test("buildPlotKnowledgePanel includes synopsis when supported", () => {
  const panel = buildPlotKnowledgePanel({
    in_library: true,
    plot_knowledge: {
      has_overview: true,
      has_synopsis: true,
      synopsis_supported: true,
      motifs: [],
      themes: ["revenge"],
      neighbor_count: 0,
    },
  });
  const synopsis = panel.layers.find((l) => l.id === "synopsis");
  assert.equal(synopsis.present, true);
  assert.deepEqual(panel.themes, ["revenge"]);
});
