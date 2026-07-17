/** Normalize Explore feed API payloads into a stable rail shape. */
export const EXPLORE_PAGE_SIZES = [20, 40, 100];
export const DEFAULT_EXPLORE_PAGE_SIZE = 20;
export const ADMIN_TASKS_PATH = "/admin/tasks";

/** Notes that mean idle caches / enrichment have not warmed yet (owner can fix in tasks). */
const OWNER_EMPTY_CTA_RULES = [
  { test: /plot_neighbors|neighbors cache|not built yet/i, label: "Warm Explore" },
  { test: /summary_motifs|plot motifs/i, label: "Run enrichment" },
  {
    test: /metadata_enrichment|not enriched|enrich release|release dates|release_date|first_air_date/i,
    label: "Run enrichment",
  },
  { test: /library sync|added_at yet/i, label: "Open Scheduled Tasks" },
];

/**
 * Owner-only primary CTA for honest empty rails that need cache/enrichment work.
 * Members/guests get the note only — no admin deep link.
 */
export function ownerEmptyStateCta(note, { isOwner = false } = {}) {
  if (!isOwner) return null;
  const text = String(note || "").trim();
  if (!text) return null;
  for (const rule of OWNER_EMPTY_CTA_RULES) {
    if (rule.test.test(text)) {
      return { label: rule.label, href: ADMIN_TASKS_PATH };
    }
  }
  return null;
}

export const EXPLORE_SECTIONS = {
  "recently-added": {
    id: "recently-added",
    title: "Recently Added",
    subtitle: "Fresh arrivals from the last 30 days",
    defaultDays: 30,
    supportsMediaType: true,
    feed: "recently-added",
  },
  "recent-releases": {
    id: "recent-releases",
    title: "Recent Releases",
    subtitle: "Library titles released in the last 90 days",
    defaultDays: 90,
    supportsMediaType: true,
    feed: "recent-releases",
  },
};

export function getExploreSectionConfig(sectionId) {
  const key = String(sectionId || "").trim();
  return EXPLORE_SECTIONS[key] || null;
}

export function normalizePageSize(raw, allowed = EXPLORE_PAGE_SIZES) {
  const value = Number(raw);
  return allowed.includes(value) ? value : DEFAULT_EXPLORE_PAGE_SIZE;
}

export function normalizeFeedOffset(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) return 0;
  return Math.floor(value);
}

export function normalizeMediaTypeFilter(raw) {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "movie" || value === "movies") return "movie";
  if (value === "show" || value === "shows" || value === "tv") return "show";
  return null;
}

/** Client-side section result sorts (feeds keep server order as default). */
export const EXPLORE_SECTION_SORTS = [
  { id: "default", label: "Default" },
  { id: "title", label: "Title" },
  { id: "year", label: "Year" },
  { id: "rating", label: "Rating" },
];

export function normalizeSectionSort(raw) {
  const value = String(raw || "").trim().toLowerCase();
  return EXPLORE_SECTION_SORTS.some((opt) => opt.id === value) ? value : "default";
}

/** Sort a page of feed items without mutating the input. */
export function sortExploreSectionItems(items, sortId) {
  const list = Array.isArray(items) ? items.slice() : [];
  const sort = normalizeSectionSort(sortId);
  if (sort === "default") return list;
  list.sort((a, b) => {
    if (sort === "title") {
      return String(a?.title || "").localeCompare(String(b?.title || ""), undefined, {
        sensitivity: "base",
      });
    }
    if (sort === "year") {
      const ay = Number(a?.year);
      const by = Number(b?.year);
      const aMissing = !Number.isFinite(ay);
      const bMissing = !Number.isFinite(by);
      if (aMissing && bMissing) return String(a?.title || "").localeCompare(String(b?.title || ""));
      if (aMissing) return 1;
      if (bMissing) return -1;
      return by - ay;
    }
    if (sort === "rating") {
      const ar = Number(a?.rating ?? a?.vote_average);
      const br = Number(b?.rating ?? b?.vote_average);
      const aMissing = !Number.isFinite(ar);
      const bMissing = !Number.isFinite(br);
      if (aMissing && bMissing) return String(a?.title || "").localeCompare(String(b?.title || ""));
      if (aMissing) return 1;
      if (bMissing) return -1;
      return br - ar;
    }
    return 0;
  });
  return list;
}

/** Parse section listing query params from URLSearchParams. */
export function parseExploreSectionQuery(searchParams) {
  const params = searchParams instanceof URLSearchParams ? searchParams : new URLSearchParams(searchParams);
  return {
    limit: normalizePageSize(params.get("limit")),
    offset: normalizeFeedOffset(params.get("offset")),
    mediaType: normalizeMediaTypeFilter(params.get("media_type")),
    sort: normalizeSectionSort(params.get("sort")),
  };
}

/** Build updated search params for section listing navigation. */
export function buildExploreSectionQuery(current, updates = {}) {
  const next = {
    limit: current?.limit ?? DEFAULT_EXPLORE_PAGE_SIZE,
    offset: current?.offset ?? 0,
    mediaType: current?.mediaType ?? null,
    sort: current?.sort ?? "default",
    ...updates,
  };
  const params = new URLSearchParams();
  if (next.mediaType) params.set("media_type", next.mediaType);
  if (next.limit !== DEFAULT_EXPLORE_PAGE_SIZE) params.set("limit", String(next.limit));
  if (next.offset > 0) params.set("offset", String(next.offset));
  if (next.sort && next.sort !== "default") params.set("sort", next.sort);
  return params;
}

export function feedPaginationSummary(payload) {
  const total = Number(payload?.total) || 0;
  const offset = normalizeFeedOffset(payload?.offset);
  const limit = Number(payload?.limit) || DEFAULT_EXPLORE_PAGE_SIZE;
  const returned = Array.isArray(payload?.items) ? payload.items.length : 0;
  const page = limit > 0 ? Math.floor(offset / limit) + 1 : 1;
  const pageCount = limit > 0 ? Math.max(1, Math.ceil(total / limit)) : 1;
  return {
    total,
    offset,
    limit,
    returned,
    page,
    pageCount,
    hasMore: Boolean(payload?.has_more) || offset + returned < total,
    hasPrev: offset > 0,
  };
}

export function normalizeFeed(payload, { fallbackNote = "Nothing to show yet." } = {}) {
  if (!payload || typeof payload !== "object") {
    return { items: [], note: fallbackNote, total: 0, meta: {} };
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  const note =
    typeof payload.note === "string" && payload.note.trim()
      ? payload.note.trim()
      : items.length
        ? null
        : fallbackNote;
  const { items: _i, note: _n, total: _t, ...meta } = payload;
  return {
    items,
    note,
    total: Number.isFinite(payload.total) ? payload.total : items.length,
    meta,
  };
}

/** Toggle a motif value in a selected list (case-sensitive values from API). */
export function toggleMotifSelection(selected, value) {
  const list = Array.isArray(selected) ? selected : [];
  const key = String(value || "").trim();
  if (!key) return list.slice();
  if (list.includes(key)) return list.filter((v) => v !== key);
  return [...list, key];
}

/** Build library query params for motif-filtered poster walls. */
export function buildMotifQueryParams(motifs, { limit = 24 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(Math.min(Math.max(1, limit), 48)));
  const cleaned = (Array.isArray(motifs) ? motifs : [])
    .map((m) => String(m || "").trim())
    .filter(Boolean);
  if (cleaned.length) params.set("motifs", cleaned.join(","));
  return params;
}

/**
 * Editorial Library Pulse stats from overview + health payloads.
 * Returns a short list suitable for a compact strip (not a full dashboard).
 */
export function buildPulseStats(overview, health) {
  const ov = overview && typeof overview === "object" ? overview : {};
  const hl = health && typeof health === "object" ? health : {};
  const stats = [];

  const total = ov.total ?? hl.total;
  if (total != null) {
    stats.push({ id: "total", label: "Titles", value: String(total) });
  }
  if (ov.movies != null) {
    stats.push({ id: "movies", label: "Movies", value: String(ov.movies) });
  }
  if (ov.shows != null) {
    stats.push({ id: "shows", label: "Shows", value: String(ov.shows) });
  }

  const unwatchedPct = hl.unwatched_pct ?? ov.unwatched_pct;
  if (unwatchedPct != null) {
    stats.push({
      id: "unwatched",
      label: "Unwatched",
      value: `${Number(unwatchedPct).toFixed(0)}%`,
    });
  }

  if (hl.stale_adds != null) {
    stats.push({
      id: "stale",
      label: "Stale adds",
      value: String(hl.stale_adds),
      detail: "Added 90+ days ago, never watched",
    });
  }

  const topGenre = Array.isArray(ov.top_genres) && ov.top_genres[0];
  if (topGenre?.genre) {
    stats.push({
      id: "genre",
      label: "Top genre",
      value: String(topGenre.genre),
      detail: topGenre.count != null ? `${topGenre.count} titles` : undefined,
    });
  }

  if (ov.avg_runtime_minutes != null) {
    stats.push({
      id: "runtime",
      label: "Avg runtime",
      value: `${Math.round(Number(ov.avg_runtime_minutes))}m`,
    });
  }

  return stats.slice(0, 7);
}

/** Extract motif chip list from `/api/library/motifs` (or facets catalog). */
export function normalizeMotifFacets(payload) {
  const facets = Array.isArray(payload?.facets) ? payload.facets : [];
  return facets
    .map((f) => ({
      value: String(f?.value || "").trim(),
      count: Number(f?.count) || 0,
    }))
    .filter((f) => f.value);
}
