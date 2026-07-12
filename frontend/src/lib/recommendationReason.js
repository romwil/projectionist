/** Internal pipeline / lookup labels — never show as "Why this?". */
const PIPELINE_RECOMMENDATION_REASONS = new Set([
  "tmdb title match",
  "tmdb search",
  "missing from your collection",
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
