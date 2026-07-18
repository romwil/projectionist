import assert from "node:assert/strict";
import test from "node:test";

import {
  buildKnowledgeCoverageRows,
  formatCoverageDetail,
  formatCoveragePct,
  summarizeKnowledgeCoverage,
} from "./knowledgeCoverage.js";

const SAMPLE = {
  total_titles: 5355,
  with_overview_pct: 99.1,
  with_motifs_pct: 99.5,
  with_keywords_pct: 92.6,
  with_themes_pct: 0,
  with_neighbors_pct: 16.1,
  with_loglines_pct: 3.2,
  avg_motifs_per_title: 8.0,
  avg_keywords_per_title: 11.4,
  avg_themes_per_title: 0,
  neighbor_edges: 8625,
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
  assert.equal(formatCoverageDetail(8625, { suffix: " edges", decimals: 0 }), "8625 edges");
  assert.equal(formatCoverageDetail(null), null);
});

test("buildKnowledgeCoverageRows omits empty themes and missing synopsis", () => {
  const rows = buildKnowledgeCoverageRows(SAMPLE);
  const ids = rows.map((r) => r.id);
  assert.ok(ids.includes("overview"));
  assert.ok(ids.includes("motifs"));
  assert.ok(ids.includes("keywords"));
  assert.ok(ids.includes("neighbors"));
  assert.ok(ids.includes("loglines"));
  assert.ok(!ids.includes("themes"));
  assert.ok(!ids.includes("synopsis"));
  const motifs = rows.find((r) => r.id === "motifs");
  assert.equal(motifs.pctLabel, "100%");
  assert.equal(motifs.detail, "8.0/title");
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
  assert.match(line, /Overview 99%/);
  assert.match(line, /Motifs 100%/);
});
