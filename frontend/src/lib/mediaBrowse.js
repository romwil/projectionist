export const MEDIA_BROWSE_COLUMNS = [
  { id: "title", label: "Title" },
  { id: "year", label: "Year" },
  { id: "media_type", label: "Type" },
  { id: "rating", label: "Rating" },
  { id: "genres", label: "Genres" },
  { id: "runtime_minutes", label: "Runtime" },
  { id: "watch_state", label: "Watch state" },
];

export const MEDIA_BROWSE_SORTS = [
  { id: "title", label: "Title" },
  { id: "year", label: "Year" },
  { id: "rating", label: "Rating" },
  { id: "added_at", label: "Recently added" },
  { id: "last_watched_at", label: "Last watched" },
  { id: "runtime_minutes", label: "Runtime" },
];

export const DEFAULT_MEDIA_BROWSE = {
  view: "poster",
  sort: "title",
  sort_dir: "asc",
  limit: 48,
  offset: 0,
  media_type: "",
  watch_state: "",
  year: "",
  genres: [],
  keywords: [],
};

const STORAGE_PREFIX = "curatorx.media-browse.columns.";

function stringList(value) {
  if (Array.isArray(value)) return value.map(String).map((item) => item.trim()).filter(Boolean);
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function numberInRange(value, fallback, min, max) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : fallback;
}

export function parseMediaBrowse(searchParams, defaults = {}) {
  const get = (key) => searchParams?.get?.(key);
  const merged = { ...DEFAULT_MEDIA_BROWSE, ...defaults };
  const view = get("view");
  const sort = get("sort");
  const sortDir = get("sort_dir");
  return {
    ...merged,
    view: view === "list" ? "list" : "poster",
    sort: MEDIA_BROWSE_SORTS.some((option) => option.id === sort) ? sort : merged.sort,
    sort_dir: sortDir === "desc" ? "desc" : "asc",
    limit: numberInRange(get("limit") || merged.limit, merged.limit, 1, 100),
    offset: numberInRange(get("offset"), 0, 0, Number.MAX_SAFE_INTEGER),
    media_type: get("media_type") || merged.media_type || "",
    watch_state: get("watch_state") || merged.watch_state || "",
    year: get("year") || merged.year || "",
    genres: stringList(get("genres") || merged.genres),
    keywords: stringList(get("keywords") || merged.keywords),
  };
}

export function buildMediaBrowseParams(state, updates = {}) {
  const next = { ...DEFAULT_MEDIA_BROWSE, ...state, ...updates };
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(next)) {
    if (key === "offset" && !value) continue;
    if (key === "view" && value === "poster") continue;
    if (key === "sort" && value === "title") continue;
    if (key === "sort_dir" && value === "asc") continue;
    if (key === "limit" && value === DEFAULT_MEDIA_BROWSE.limit) continue;
    const normalized = Array.isArray(value) ? stringList(value).join(",") : String(value || "").trim();
    if (normalized) params.set(key, normalized);
  }
  return params;
}

export function queryFiltersFromBrowse(state, extra = {}) {
  const filters = { ...extra };
  for (const key of ["sort", "sort_dir", "limit", "offset", "media_type", "watch_state", "year", "genres", "keywords"]) {
    const value = state?.[key];
    if (Array.isArray(value) ? value.length : value !== "" && value != null) filters[key] = value;
  }
  return filters;
}

export function loadMediaBrowseColumns(scope = "default") {
  try {
    const stored = JSON.parse(localStorage.getItem(`${STORAGE_PREFIX}${scope}`) || "null");
    if (Array.isArray(stored) && stored.length) return stored.filter((id) => MEDIA_BROWSE_COLUMNS.some((column) => column.id === id));
  } catch {
    // Browser storage is optional.
  }
  return MEDIA_BROWSE_COLUMNS.map((column) => column.id);
}

export function saveMediaBrowseColumns(scope, columns) {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${scope}`, JSON.stringify(stringList(columns)));
  } catch {
    // Private browsing or quota failures should not prevent browsing.
  }
}

export function libraryExportHref(state, columns = []) {
  const params = buildMediaBrowseParams(state);
  if (columns.length) params.set("columns", columns.join(","));
  return `/api/library/export.csv?${params.toString()}`;
}
