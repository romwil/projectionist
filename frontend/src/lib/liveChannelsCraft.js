/** Shared craft filter helpers for Admin Live Channels craft + station Settings. */

/** Filter Plex / published collections for craft pickers (media scope + search). */
export function filterLiveCollections(
  collections,
  { mediaScope = "both", filterQuery = "", selectedId = "" } = {},
) {
  const rows = Array.isArray(collections) ? collections : [];
  const scopeFiltered =
    mediaScope === "both"
      ? rows
      : rows.filter((row) => {
          const mt = String(row.media_type || "").toLowerCase();
          if (!mt) return true;
          if (mediaScope === "tv") return mt === "show" || mt === "shows" || mt === "tv";
          if (mediaScope === "movies") return mt === "movie" || mt === "movies";
          return true;
        });
  const q = String(filterQuery || "").trim().toLowerCase();
  const filtered = !q
    ? scopeFiltered
    : scopeFiltered.filter((row) => {
        const hay = `${row.title || ""} ${row.label || ""} ${row.source || ""}`.toLowerCase();
        return hay.includes(q);
      });
  if (selectedId && !filtered.some((row) => row.id === selectedId)) {
    const selected = rows.find((row) => row.id === selectedId);
    if (selected) return [selected, ...filtered];
  }
  return filtered;
}

export function findLiveCollection(collections, collectionId) {
  if (!collectionId) return null;
  return (Array.isArray(collections) ? collections : []).find((row) => row.id === collectionId) || null;
}

export function collectionPublishButtonLabel({
  selected,
  busy = false,
  publishingLabel = "Publishing…",
  idlePrefix = "Publish",
  emptyLabel = "Select a collection to publish",
}) {
  if (busy) return publishingLabel;
  if (!selected?.title) return emptyLabel;
  return `${idlePrefix} “${selected.title}”`;
}

export function buildCraftFiltersPayload(craft) {
  const genres = Array.isArray(craft?.genres)
    ? craft.genres.filter(Boolean)
    : craft?.genre
      ? [craft.genre]
      : [];
  const decadeRaw = craft?.decade;
  const decade =
    decadeRaw === "" || decadeRaw == null ? undefined : Number(decadeRaw);
  const theme = String(craft?.theme || "").trim();
  const rating = String(craft?.content_rating || "").trim();
  const payload = {};
  if (genres.length) payload.genres = genres;
  if (Number.isFinite(decade)) payload.decade = decade;
  if (theme) payload.themes = [theme];
  if (rating) payload.content_ratings = [rating];
  return payload;
}

/** Draft form state from status/station_meta for Settings read/write. */
export function craftDraftFromStation(station = {}) {
  const filters = station?.craft_filters || {};
  const genres = Array.isArray(filters.genres) ? filters.genres.filter(Boolean) : [];
  return {
    media_scope: station?.media_scope || "both",
    subtitles_enabled: Boolean(station?.subtitles_enabled),
    source: station?.source || "",
    motif: station?.motif || "",
    cluster_tag: station?.cluster_tag || "",
    collection_title: station?.collection_title || "",
    programming_mode: station?.programming_mode || "",
    genres,
    decade: filters.decade == null || filters.decade === "" ? "" : String(filters.decade),
    theme: Array.isArray(filters.themes) && filters.themes[0] ? String(filters.themes[0]) : "",
    content_rating:
      Array.isArray(filters.content_ratings) && filters.content_ratings[0]
        ? String(filters.content_ratings[0])
        : "",
  };
}
