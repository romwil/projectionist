/**
 * Format library knowledge-coverage payloads for Admin / Explore UI.
 * Consumes GET /api/library/knowledge-coverage (or stats.knowledge_coverage).
 */

/** Ordered metric keys shown in the coverage strip (optional keys omitted when absent). */
export const KNOWLEDGE_COVERAGE_METRICS = [
  {
    id: "overview",
    pctKey: "with_overview_pct",
    label: "Overview",
    detailKey: null,
    detailSuffix: null,
  },
  {
    id: "motifs",
    pctKey: "with_motifs_pct",
    label: "Motifs",
    detailKey: "avg_motifs_per_title",
    detailSuffix: "/title",
  },
  {
    id: "keywords",
    pctKey: "with_keywords_pct",
    label: "Keywords",
    detailKey: "avg_keywords_per_title",
    detailSuffix: "/title",
  },
  {
    id: "themes",
    pctKey: "with_themes_pct",
    label: "Themes",
    detailKey: "avg_themes_per_title",
    detailSuffix: "/title",
    /** Hide when zero and no theme rows (Phase C not populated yet). */
    omitWhenEmpty: true,
  },
  {
    id: "neighbors",
    pctKey: "with_neighbors_pct",
    label: "Neighbors",
    detailKey: "neighbor_edges",
    detailSuffix: " edges",
  },
  {
    id: "loglines",
    pctKey: "with_loglines_pct",
    label: "Loglines",
    detailKey: "logline_count",
    detailSuffix: " titles",
  },
  {
    id: "synopsis",
    pctKey: "with_synopsis_pct",
    label: "Synopsis",
    detailKey: "synopsis_count",
    detailSuffix: " titles",
    /** Only present when long_synopsis column exists (Phase C). */
    requireKey: "with_synopsis_pct",
  },
];

/** Format a coverage percentage for display (e.g. 42.5 → "43%"). */
export function formatCoveragePct(value) {
  if (value == null || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const rounded = Math.round(num);
  return `${rounded}%`;
}

/** Format average or count details under a coverage metric. */
export function formatCoverageDetail(value, { suffix = "", decimals = 1 } = {}) {
  if (value == null || value === "") return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const text = decimals === 0 ? String(Math.round(num)) : num.toFixed(decimals);
  return suffix ? `${text}${suffix}` : text;
}

/**
 * Normalize API coverage into display rows.
 * Gracefully omits themes when empty and synopsis when the key is absent.
 */
export function buildKnowledgeCoverageRows(coverage) {
  if (!coverage || typeof coverage !== "object") return [];
  const rows = [];
  for (const metric of KNOWLEDGE_COVERAGE_METRICS) {
    if (metric.requireKey && !(metric.requireKey in coverage)) continue;
    const pct = Number(coverage[metric.pctKey]);
    if (!Number.isFinite(pct)) continue;
    if (metric.omitWhenEmpty) {
      const themeRows = Number(coverage.theme_rows) || 0;
      if (pct <= 0 && themeRows <= 0) continue;
    }
    let detail = null;
    if (metric.detailKey && coverage[metric.detailKey] != null) {
      const decimals = metric.detailKey.startsWith("avg_") ? 1 : 0;
      detail = formatCoverageDetail(coverage[metric.detailKey], {
        suffix: metric.detailSuffix || "",
        decimals,
      });
    }
    rows.push({
      id: metric.id,
      label: metric.label,
      pct,
      pctLabel: formatCoveragePct(pct),
      detail,
    });
  }
  return rows;
}

/** One-line honesty summary for Explore (e.g. "Motifs 99% · Neighbors 16%"). */
export function summarizeKnowledgeCoverage(coverage, { maxMetrics = 4 } = {}) {
  const rows = buildKnowledgeCoverageRows(coverage);
  if (!rows.length) return null;
  const total = Number(coverage?.total_titles);
  const head = Number.isFinite(total) && total > 0 ? `${total.toLocaleString()} titles` : null;
  const bits = rows.slice(0, maxMetrics).map((row) => `${row.label} ${row.pctLabel}`);
  return [head, bits.join(" · ")].filter(Boolean).join(" · ");
}
