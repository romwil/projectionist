import assert from "node:assert/strict";
import test from "node:test";

import {
  KNOWLEDGE_COVERAGE_REQUEST_MS,
  buildKnowledgeCoverageRows,
  embeddingCoverageLabel,
  formatCoverageDetail,
  formatCoveragePct,
  knowledgeCoverageFailureCopy,
  knowledgeStripContent,
  summarizeKnowledgeCoverage,
} from "./knowledgeCoverage.js";

const SAMPLE = {
  total_titles: 5355,
  with_overview_pct: 99.1,
  with_motifs_pct: 99.5,
  with_keywords_pct: 92.6,
  with_themes_pct: 0,
  with_neighbors_pct: 16.1,
  with_explainable_neighbors_pct: 4.2,
  with_loglines_pct: 3.2,
  avg_motifs_per_title: 8.0,
  avg_keywords_per_title: 11.4,
  avg_themes_per_title: 0,
  neighbor_edges: 8625,
  explainable_neighbor_edges: 1200,
  motif_rows: 42581,
  keyword_rows: 61185,
  theme_rows: 0,
  logline_count: 171,
};

test("formatCoveragePct rounds and guards non-finite", () => {
  assert.equal(formatCoveragePct(99.1), "99%");
  assert.equal(formatCoveragePct(16.6), "17%");
  assert.equal(formatCoveragePct(null), "—");
  assert.equal(formatCoveragePct(undefined), "—");
});

test("formatCoverageDetail formats averages and counts", () => {
  assert.equal(formatCoverageDetail(8, { suffix: "/title", decimals: 1 }), "8.0/title");
  assert.equal(
    formatCoverageDetail(8625, { suffix: " similarity links", decimals: 0 }),
    "8625 similarity links",
  );
  assert.equal(formatCoverageDetail(null), null);
});

test("buildKnowledgeCoverageRows omits empty themes and missing synopsis", () => {
  const rows = buildKnowledgeCoverageRows(SAMPLE);
  const ids = rows.map((r) => r.id);
  assert.equal(ids[0], "explainableNeighbors");
  assert.equal(ids[1], "neighbors");
  assert.ok(ids.includes("overview"));
  assert.ok(ids.includes("motifs"));
  assert.ok(ids.includes("keywords"));
  assert.ok(ids.includes("loglines"));
  assert.ok(!ids.includes("themes"));
  assert.ok(!ids.includes("synopsis"));
  const motifs = rows.find((r) => r.id === "motifs");
  assert.equal(motifs.pctLabel, "100%");
  assert.equal(motifs.detail, "8.0/title");
  const similarTitles = rows.find((r) => r.id === "neighbors");
  assert.equal(similarTitles.label, "Similar cache");
  assert.equal(similarTitles.detail, "8625 cosine links");
  const named = rows.find((r) => r.id === "explainableNeighbors");
  assert.equal(named.label, "Named kinship");
  assert.equal(named.detail, "1200 explainable links");
  assert.equal(named.pctLabel, "4%");
});

test("buildKnowledgeCoverageRows includes themes and synopsis when present", () => {
  const rows = buildKnowledgeCoverageRows({
    ...SAMPLE,
    with_themes_pct: 12.5,
    theme_rows: 400,
    avg_themes_per_title: 0.4,
    with_synopsis_pct: 5.0,
    synopsis_count: 268,
  });
  const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
  assert.equal(byId.themes.pctLabel, "13%");
  assert.equal(byId.themes.detail, "0.4/title");
  assert.equal(byId.synopsis.pctLabel, "5%");
  assert.equal(byId.synopsis.detail, "268 titles");
});

test("buildKnowledgeCoverageRows returns empty for null payload", () => {
  assert.deepEqual(buildKnowledgeCoverageRows(null), []);
  assert.deepEqual(buildKnowledgeCoverageRows(undefined), []);
});

test("summarizeKnowledgeCoverage builds explore honesty line", () => {
  const line = summarizeKnowledgeCoverage(SAMPLE, { maxMetrics: 3 });
  assert.match(line, /5,355 titles/);
  assert.match(line, /Named kinship 4%/);
  assert.match(line, /Similar cache/);
});

test("embeddingCoverageLabel is honest about hash-fallback vectors", () => {
  assert.equal(
    embeddingCoverageLabel({ embedding_is_hash_fallback: true, embedding_model: "hash-fallback" }),
    "Vectors: local hash embeddings (no embedding API)",
  );
  assert.equal(
    embeddingCoverageLabel({ embedding_is_hash_fallback: false, embedding_model: "text-embedding-3-small" }),
    "Vectors: text-embedding-3-small",
  );
  assert.equal(embeddingCoverageLabel({}), null);
});

test("optional coverage failure does not surface Failed to fetch", () => {
  const transport = new TypeError("Failed to fetch");
  assert.equal(knowledgeCoverageFailureCopy(transport), "");
  const aborted = new Error("The operation was aborted.");
  aborted.name = "AbortError";
  assert.equal(knowledgeCoverageFailureCopy(aborted), "");
  assert.equal(knowledgeCoverageFailureCopy(new TypeError("Load failed")), "");

  const hidden = knowledgeStripContent({
    loading: false,
    error: "Failed to fetch",
    summary: null,
  });
  assert.equal(hidden, null);
  assert.equal(String(hidden || "").includes("Failed to fetch"), false);

  // A stored transport string must not paint even if a summary is also present.
  assert.equal(
    knowledgeStripContent({
      loading: false,
      error: transport.message,
      summary: "5,632 titles · Overview 99%",
    }),
    null,
  );
});

test("coverage strip does not wait on the explore hub", () => {
  // The strip's content is its own fetch. Hub loading is not an input, and the
  // request bound is short enough that a hung coverage call cannot sit on the page.
  assert.equal(KNOWLEDGE_COVERAGE_REQUEST_MS > 0, true);
  assert.equal(KNOWLEDGE_COVERAGE_REQUEST_MS <= 8000, true);
  const line = knowledgeStripContent({
    loading: false,
    error: "",
    summary: summarizeKnowledgeCoverage(SAMPLE),
  });
  assert.match(line, /titles/);
  assert.equal(line.includes("Failed to fetch"), false);
  assert.equal(knowledgeStripContent({ loading: true, error: "", summary: line }), null);
});
