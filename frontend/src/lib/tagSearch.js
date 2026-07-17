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

/** Arrow-key highlight index for typeahead chip lists. */
export function moveTypeaheadIndex(current, key, length) {
  const len = Math.max(0, Number(length) || 0);
  if (len <= 0) return -1;
  const cur = Number.isFinite(current) ? current : -1;
  if (key === "ArrowDown") return cur < 0 ? 0 : Math.min(len - 1, cur + 1);
  if (key === "ArrowUp") return cur <= 0 ? len - 1 : cur - 1;
  if (key === "Home") return 0;
  if (key === "End") return len - 1;
  return cur;
}

export function toggleTagSelection(selected, value) {
  const list = Array.isArray(selected) ? selected : [];
  const key = String(value || "").trim();
  if (!key) return list.slice();
  if (list.includes(key)) return list.filter((v) => v !== key);
  return [...list, key];
}

/** Build AND-filter path: primary tag in path, extras in ?and= */
export function buildAndTagPath(tagPathFn, selected) {
  const tags = (Array.isArray(selected) ? selected : [])
    .map((t) => String(t || "").trim())
    .filter(Boolean);
  if (!tags.length) return null;
  const primary = tagPathFn(tags[0]);
  if (!primary) return null;
  if (tags.length === 1) return primary;
  const params = new URLSearchParams();
  params.set("and", tags.slice(1).join(","));
  return `${primary}?${params.toString()}`;
}

export function parseAndTags(searchParams) {
  const params =
    searchParams instanceof URLSearchParams
      ? searchParams
      : new URLSearchParams(searchParams || "");
  return String(params.get("and") || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export const TAG_SORT_OPTIONS = [
  { id: "title", label: "Title", sort: "title" },
  { id: "year", label: "Year", sort: "year" },
  { id: "added", label: "Recently added", sort: "added_at" },
  { id: "rating", label: "Rating", sort: "vote_average" },
];

export function normalizeTagSort(raw) {
  const value = String(raw || "").trim().toLowerCase();
  const match = TAG_SORT_OPTIONS.find((opt) => opt.sort === value || opt.id === value);
  return match ? match.sort : "title";
}
