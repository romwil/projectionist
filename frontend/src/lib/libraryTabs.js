/** Unified Library hub tab routing (`/library?tab=…`). */

export const LIBRARY_TAB_PARAM = "tab";

export const LIBRARY_TABS = [
  { id: "shelves", label: "Shelves", testId: "library-tab-shelves" },
  { id: "watchlist", label: "Watchlist", testId: "library-tab-watchlist" },
  { id: "collections", label: "Collections", testId: "library-tab-collections" },
  { id: "browse", label: "Browse", testId: "library-tab-browse" },
];

export const DEFAULT_LIBRARY_TAB = "shelves";

const TAB_IDS = new Set(LIBRARY_TABS.map((tab) => tab.id));

export function parseLibraryTab(searchParams) {
  const raw = String(searchParams?.get?.(LIBRARY_TAB_PARAM) || "")
    .trim()
    .toLowerCase();
  return TAB_IDS.has(raw) ? raw : DEFAULT_LIBRARY_TAB;
}

export function libraryHubPath(tab = DEFAULT_LIBRARY_TAB, extra = {}) {
  const params = new URLSearchParams();
  const resolved = String(tab || "").trim().toLowerCase();
  if (resolved && resolved !== DEFAULT_LIBRARY_TAB && TAB_IDS.has(resolved)) {
    params.set(LIBRARY_TAB_PARAM, resolved);
  }
  for (const [key, value] of Object.entries(extra || {})) {
    if (value == null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `/library?${qs}` : "/library";
}

export function librarySavedPath() {
  return "/library/saved";
}

export function libraryShelvesDetailPath(listId) {
  return `/library/shelves/${encodeURIComponent(String(listId))}`;
}

export function libraryCollectionsDetailPath(listId) {
  return `/library/collections/${encodeURIComponent(String(listId))}`;
}
