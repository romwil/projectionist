/** Tag / facet search helpers (full-index API, not on-screen chips only). */

export function normalizeFacetHits(payload) {
  const facets = Array.isArray(payload?.facets) ? payload.facets : [];
  return facets
    .map((entry) => ({
      value: String(entry.value || entry.name || "").trim(),
      count: Number(entry.count || 0) || 0,
    }))
    .filter((entry) => entry.value);
}

export function shouldQueryFacetIndex(query, { minChars = 2 } = {}) {
  return String(query || "").trim().length >= minChars;
}

export function tagSearchEmptyMessage(query, { searching = false } = {}) {
  const q = String(query || "").trim();
  if (!q) return "";
  if (searching) return "Searching tags…";
  return `No library tags match “${q}”.`;
}
