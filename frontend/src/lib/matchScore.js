/**
 * Format a recommendation / neighbor match as a percent badge label.
 * Accepts 0–1 fractions or 0–100 percentages from common score fields.
 * @param {unknown} item
 * @returns {string} e.g. "87% Match", or "" when no usable score
 */
export function formatMatchPercent(item) {
  if (!item || typeof item !== "object") return "";
  const raw =
    item.match_pct ??
    item.match_score ??
    item.taste_match ??
    item.score ??
    item.similarity;
  if (raw == null || raw === "") return "";
  const num = Number(raw);
  if (!Number.isFinite(num)) return "";
  let pct = num;
  if (num >= 0 && num <= 1) pct = num * 100;
  if (pct < 0 || pct > 100) return "";
  const rounded = Math.round(pct);
  if (rounded <= 0) return "";
  return `${rounded}% Match`;
}
