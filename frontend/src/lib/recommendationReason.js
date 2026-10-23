/** Internal pipeline / lookup labels — never show as "Why this?". */
const PIPELINE_RECOMMENDATION_REASONS = new Set([
  "tmdb title match",
  "tmdb search",
  "missing from your collection",
  // Legacy double-feature slot labels — never useful as "Why this?".
  "double feature — first half",
  "double feature — second half",
  "double feature - first half",
  "double feature - second half",
  "unwatched pick for you",
  "good pick for tonight",
  "in your library",
  "strong plot kinship",
  "related title",
]);

/** Arrival kinds that may show a poster why line (XC-01). Missing kind → no line. */
export const BRIDGE_EXPLANATION_KINDS = new Set([
  "watched_bridge",
  "plot_link",
  "collection",
  "shared_crew",
  "directed_by",
  "written_by",
]);

/**
 * Prefer human curator rationale; drop empty or internal pipeline labels.
 * @param {unknown} reason
 * @returns {string}
 */
export function displayRecommendationReason(reason) {
  const text = String(reason || "").trim();
  if (!text) return "";
  if (PIPELINE_RECOMMENDATION_REASONS.has(text.toLowerCase())) return "";
  return text;
}

/**
 * Poster why line only when the card arrived via a named bridge.
 * Browse walls pass no explanation and stay why-less.
 * @param {Record<string, unknown> | null | undefined} item
 * @returns {string}
 */
export function posterWhyLine(item) {
  if (!item || typeof item !== "object") return "";
  const explanation =
    item.explanation && typeof item.explanation === "object"
      ? item.explanation
      : item.why && typeof item.why === "object" && item.why.explanation
        ? item.why.explanation
        : null;
  const kind = String(explanation?.kind || "").trim().toLowerCase();
  if (!BRIDGE_EXPLANATION_KINDS.has(kind)) return "";
  return displayRecommendationReason(explanation?.sentence);
}
