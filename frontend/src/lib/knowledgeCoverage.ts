import type {JsonObject, JsParam} from "../api/types";
/**
 * Format library knowledge-coverage payloads for Admin / Explore UI.
 * Consumes GET /api/library/knowledge-coverage (or stats.knowledge_coverage).
 */

/** Ordered metric keys shown in the coverage strip (optional keys omitted when absent).
 * Named kinship leads — that is the health that matters for More Like This. */
export const KNOWLEDGE_COVERAGE_METRICS = [
  {
    id: "openedExplainableNeighbors",
    pctKey: "with_explainable_neighbors_opened_pct",
    label: "Named kinship (opened)",
    detailKey: "opened_title_count",
    detailSuffix: " opened titles",
    requireKey: "with_explainable_neighbors_opened_pct",
    omitUnlessCount: "opened_title_count",
  },
  {
    id: "explainableNeighbors",
    pctKey: "with_explainable_neighbors_pct",
    label: "Named kinship",
    detailKey: "explainable_neighbor_edges",
    detailSuffix: " explainable links",
  },
  {
    id: "neighbors",
    pctKey: "with_neighbors_pct",
    label: "Similar cache",
    detailKey: "neighbor_edges",
    detailSuffix: " cosine links",
  },
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
export function formatCoveragePct(value: unknown) {
  if (value == null || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const rounded = Math.round(num);
  return `${rounded}%`;
}

/** Format average or count details under a coverage metric. */
export function formatCoverageDetail(value: unknown, { suffix = "", decimals = 1 }: JsParam = {}) {
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
export function buildKnowledgeCoverageRows(coverage: JsParam) {
  if (!coverage || typeof coverage !== "object") return [];
  const rows: JsParam[] = [];
  for (const metric of KNOWLEDGE_COVERAGE_METRICS) {
    if (metric.requireKey && !(metric.requireKey in coverage)) continue;
    if (metric.omitUnlessCount && !(Number(coverage[metric.omitUnlessCount]) > 0)) continue;
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

/** One-line honesty summary for Explore (e.g. "Motifs 99% · Similar titles 16%"). */
export function summarizeKnowledgeCoverage(coverage: JsParam, { maxMetrics = 4 }: JsParam = {}) {
  const rows = buildKnowledgeCoverageRows(coverage);
  if (!rows.length) return null;
  const total = Number(coverage?.total_titles);
  const head = Number.isFinite(total) && total > 0 ? `${total.toLocaleString()} titles` : null;
  const bits = rows.slice(0, maxMetrics).map((row) => `${(row as JsParam).label} ${(row as JsParam).pctLabel}`);
  return [head, bits.join(" · ")].filter(Boolean).join(" · ");
}

/**
 * Honest embedding-model label for coverage UI.
 * When vectors are hash-fallback (no embedding API), say so — never imply a remote model.
 */
export function embeddingCoverageLabel(coverage: JsParam) {
  if (!coverage || typeof coverage !== "object") return null;
  if (coverage.embedding_is_hash_fallback) {
    return "Vectors: local hash embeddings (no embedding API)";
  }
  const model = String(coverage.embedding_model || "").trim();
  if (!model) return null;
  return `Vectors: ${model}`;
}

/**
 * Bound for the optional coverage fetch. The Explore hub does not wait on it;
 * this only stops a hung socket from sitting open.
 */
export const KNOWLEDGE_COVERAGE_REQUEST_MS = 8000;

const TRANSPORT_FAILURE_RE = /failed to fetch|load failed|networkerror|network error|failed to load/i;

/**
 * Copy for a coverage fetch failure. Browser transport errors ("Failed to fetch",
 * abort, Safari "Load failed") stay blank so optional UI can degrade quietly.
 */
export function knowledgeCoverageFailureCopy(error: unknown) {
  if (!error) return "";
  const name = String((error as JsParam).name || "");
  const message = String((error as JsParam).message || "").trim();
  if (name === "AbortError" || name === "TypeError" || TRANSPORT_FAILURE_RE.test(message)) {
    return "";
  }
  return message;
}

/**
 * Explore footer strip. Independent of hub loading: render only a real summary.
 * A failed optional request returns null and must not paint a raw error string.
 */
export function knowledgeStripContent({ loading = false, error = "", summary = null }: JsParam = {}) {
  if (loading) return null;
  if (error || TRANSPORT_FAILURE_RE.test(String(error || ""))) return null;
  if (!summary) return null;
  const text = String(summary);
  if (TRANSPORT_FAILURE_RE.test(text)) return null;
  return text;
}
