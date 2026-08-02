/**
 * Progressive (as-you-type) library browse search.
 * Writes the existing `q` URL param so LibraryBrowsePage’s queryLibrary path
 * filters the grid; empty query clears `q` and restores full browse.
 */

/** Light debounce before committing draft → URL (coalesces keystrokes). */
export const BROWSE_SEARCH_DEBOUNCE_MS = 200;

export function normalizeBrowseSearchQuery(value) {
  return String(value ?? "").trim();
}

/**
 * Next URL `q` from an input draft, or `null` when the URL already matches
 * (no progressive update). Empty string means clear search → full browse.
 */
export function nextBrowseSearchQuery(draft, urlQ) {
  const next = normalizeBrowseSearchQuery(draft);
  const current = normalizeBrowseSearchQuery(urlQ);
  if (next === current) return null;
  return next;
}

/** Set or delete `q` on browse search params. */
export function setBrowseSearchQueryParam(params, q) {
  const next = normalizeBrowseSearchQuery(q);
  if (next) params.set("q", next);
  else params.delete("q");
  return params;
}
