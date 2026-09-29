export const MEDIA_BROWSE_COLUMNS = [
  { id: "title", label: "Title" },
  { id: "year", label: "Year" },
  { id: "media_type", label: "Type" },
  { id: "vote_average", label: "Rating" },
  { id: "genres", label: "Genres" },
  { id: "runtime_minutes", label: "Runtime" },
  { id: "watch_state", label: "Watch state" },
];

export const MEDIA_BROWSE_SORTS = [
  { id: "title", label: "Title" },
  { id: "year", label: "Year" },
  { id: "vote_average", label: "Rating" },
  { id: "added_at", label: "Recently added" },
  { id: "episode_added_at", label: "Recently added episodes" },
  { id: "last_viewed_at", label: "Last watched" },
  { id: "runtime_minutes", label: "Runtime" },
];

/** Sort options for TV browse — episode arrivals first in the list. */
export const MEDIA_BROWSE_TV_SORTS = [
  { id: "episode_added_at", label: "Recently added episodes" },
  { id: "added_at", label: "Recently added shows" },
  { id: "title", label: "Title" },
  { id: "year", label: "Year" },
  { id: "vote_average", label: "Rating" },
  { id: "last_viewed_at", label: "Last watched" },
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

/** Default browse state when opening the TV library (fresh-episode browsing). */
export const DEFAULT_TV_MEDIA_BROWSE = {
  ...DEFAULT_MEDIA_BROWSE,
  media_type: "show",
  sort: "episode_added_at",
  sort_dir: "desc",
};

/** Page sizes surfaced in the shared "Show" selector. "all" is a capped fetch. */
export const MEDIA_BROWSE_PAGE_SIZES = [48, 100, 500, "all"];

/**
 * Ceiling for an "All" request. Mirrors the CSV export cap in
 * projectionist/web/app.py so "All" never asks the reader for an unbounded payload.
 */
export const MEDIA_BROWSE_ALL_CAP = 5000;

const STORAGE_PREFIX = "projectionist.media-browse.columns.";

/** True when a page-size value represents the capped "All" selection. */
export function isAllPageSize(value) {
  return String(value ?? "").trim().toLowerCase() === "all";
}

/**
 * Resolve a page-size selection to the concrete request limit.
 * "All" becomes min(total_matched, MEDIA_BROWSE_ALL_CAP) — or the cap when the
 * total is unknown — so a single request returns every visible row up to the
 * ceiling. Fixed sizes are clamped to the same ceiling.
 */
export function resolvePageSizeLimit(pageSize, totalMatched) {
  if (isAllPageSize(pageSize)) {
    const total = Number(totalMatched);
    if (Number.isFinite(total) && total > 0) return Math.min(total, MEDIA_BROWSE_ALL_CAP);
    return MEDIA_BROWSE_ALL_CAP;
  }
  const parsed = Number(pageSize);
  if (Number.isFinite(parsed) && parsed > 0) return Math.min(parsed, MEDIA_BROWSE_ALL_CAP);
  return DEFAULT_MEDIA_BROWSE.limit;
}

function stringList(value) {
  if (Array.isArray(value)) return value.map(String).map((item) => item.trim()).filter(Boolean);
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function numberInRange(value, fallback, min, max) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : fallback;
}

/** Parse a page-size URL value into "all" or a bounded number. */
function parsePageSizeParam(value, fallback) {
  if (value == null || value === "") return fallback;
  if (isAllPageSize(value)) return "all";
  return numberInRange(value, fallback, 1, MEDIA_BROWSE_ALL_CAP);
}

export function parseMediaBrowse(searchParams, defaults = {}) {
  const get = (key) => searchParams?.get?.(key);
  const mediaHint = String(get("media_type") || defaults.media_type || "").trim().toLowerCase();
  const baseDefaults =
    mediaHint === "show" || mediaHint === "tv"
      ? { ...DEFAULT_TV_MEDIA_BROWSE, ...defaults }
      : { ...DEFAULT_MEDIA_BROWSE, ...defaults };
  const merged = baseDefaults;
  const view = get("view");
  const sort = get("sort");
  const sortDir = get("sort_dir");
  const allowedSorts = mediaHint === "show" || mediaHint === "tv" ? MEDIA_BROWSE_TV_SORTS : MEDIA_BROWSE_SORTS;
  const defaultSortDir = merged.sort_dir === "desc" ? "desc" : "asc";
  return {
    ...merged,
    view: view === "list" ? "list" : "poster",
    sort: allowedSorts.some((option) => option.id === sort)
      ? sort
      : MEDIA_BROWSE_SORTS.some((option) => option.id === sort)
        ? sort
        : merged.sort,
    sort_dir: sortDir === "desc" || sortDir === "asc" ? sortDir : defaultSortDir,
    limit: parsePageSizeParam(get("limit") || merged.limit, merged.limit),
    offset: numberInRange(get("offset"), 0, 0, Number.MAX_SAFE_INTEGER),
    media_type: get("media_type") || merged.media_type || "",
    watch_state: get("watch_state") || merged.watch_state || "",
    year: get("year") || merged.year || "",
    genres: stringList(get("genres") || merged.genres),
    keywords: stringList(get("keywords") || merged.keywords),
  };
}

export function buildMediaBrowseParams(state, updates = {}) {
  const mediaHint = String(updates.media_type ?? state?.media_type ?? "").trim().toLowerCase();
  const defaults =
    mediaHint === "show" || mediaHint === "tv" ? DEFAULT_TV_MEDIA_BROWSE : DEFAULT_MEDIA_BROWSE;
  const next = { ...defaults, ...state, ...updates };
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(next)) {
    if (key === "offset" && !value) continue;
    if (key === "view" && value === "poster") continue;
    if (key === "sort" && value === defaults.sort) continue;
    if (key === "sort_dir" && value === defaults.sort_dir) continue;
    if (key === "limit" && value === DEFAULT_MEDIA_BROWSE.limit) continue;
    const normalized = Array.isArray(value) ? stringList(value).join(",") : String(value || "").trim();
    if (normalized) params.set(key, normalized);
  }
  return params;
}

export function queryFiltersFromBrowse(state, extra = {}) {
  const filters = { ...extra };
  for (const key of ["sort", "sort_dir", "limit", "offset", "media_type", "year", "genres", "keywords"]) {
    const value = state?.[key];
    if (Array.isArray(value) ? value.length : value !== "" && value != null) filters[key] = value;
  }
  // Never forward the "all" sentinel to the reader — resolve it to the cap.
  if (isAllPageSize(filters.limit)) filters.limit = MEDIA_BROWSE_ALL_CAP;
  if (state?.watch_state === "unwatched") filters.unwatched_only = true;
  if (state?.watch_state === "watched") filters.min_view_count = 1;
  if (state?.watch_state === "in_progress") filters.in_progress_only = true;
  return filters;
}

export function mediaBrowseWatchState(item) {
  const explicit = String(item?.watch_state || "").toLowerCase();
  const watched = Boolean(item?.watched || Number(item?.view_count) > 0 || explicit === "watched");
  if (watched) return "watched";
  const inProgress = Boolean(
    item?.view_offset ||
    item?.view_offset_ms ||
    explicit === "partial" ||
    explicit === "in_progress",
  );
  return inProgress ? "in_progress" : "unwatched";
}

export function matchesMediaBrowseWatchState(item, watchState) {
  return !watchState || mediaBrowseWatchState(item) === watchState;
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

/** Serialize the currently visible local collection without widening its scope. */
export function mediaBrowseRowsToCsv(items, columns) {
  const quote = (value) => {
    const isList = Array.isArray(value);
    const text = isList ? value.join(" · ") : String(value ?? "");
    return isList || /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const valueFor = (item, column) => {
    if (column === "watch_state") {
      return mediaBrowseWatchState(item).replace("_", " ").replace(/^./, (char) => char.toUpperCase());
    }
    if (column === "vote_average") return item?.vote_average ?? item?.rating ?? "";
    return item?.[column] ?? "";
  };
  return [
    columns.join(","),
    ...(items || []).map((item) => columns.map((column) => quote(valueFor(item, column))).join(",")),
  ].join("\n");
}
