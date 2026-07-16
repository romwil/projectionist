/** Normalize Explore feed API payloads into a stable rail shape. */
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
