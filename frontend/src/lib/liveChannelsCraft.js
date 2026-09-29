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

/** Ensure a <select> option list includes the currently saved value (edit load). */
export function withSelectedOption(options, value, { label } = {}) {
  const rows = Array.isArray(options) ? [...options] : [];
  if (value == null || value === "") return rows;
  const v = String(value);
  if (rows.some((row) => String(row?.value) === v)) return rows;
  return [{ value: v, label: label || v, count: 0 }, ...rows];
}

export function emptyFilterGroup() {
  return {
    genres: [],
    decade: "",
    theme: "",
    motif: "",
    content_rating: "",
  };
}

function groupFromFilters(filters = {}) {
  const genres = Array.isArray(filters.genres) ? filters.genres.filter(Boolean) : [];
  const themes = Array.isArray(filters.themes) ? filters.themes.filter(Boolean) : [];
  const motifs = Array.isArray(filters.motifs) ? filters.motifs.filter(Boolean) : [];
  const ratings = Array.isArray(filters.content_ratings)
    ? filters.content_ratings.filter(Boolean)
    : [];
  return {
    genres,
    decade: filters.decade == null || filters.decade === "" ? "" : String(filters.decade),
    theme: themes[0] ? String(themes[0]) : "",
    motif: motifs[0] ? String(motifs[0]) : "",
    content_rating: ratings[0] ? String(ratings[0]) : "",
  };
}

function groupHasFilters(group) {
  if (!group) return false;
  return Boolean(
    (Array.isArray(group.genres) && group.genres[0]) ||
      group.decade ||
      group.theme ||
      group.motif ||
      group.content_rating,
  );
}

/** Parse station_meta / API craft_filters into UI filter groups (DNF). */
export function filterGroupsFromCraftFilters(craftFilters) {
  const raw = craftFilters && typeof craftFilters === "object" ? craftFilters : {};
  if (Array.isArray(raw.groups) && raw.groups.length) {
    const groups = raw.groups.map((g) => groupFromFilters(g)).filter(groupHasFilters);
    return groups.length ? groups : [emptyFilterGroup()];
  }
  const single = groupFromFilters(raw);
  return groupHasFilters(single) ? [single] : [emptyFilterGroup()];
}

function payloadFromGroup(group) {
  const genres = Array.isArray(group?.genres)
    ? group.genres.filter(Boolean)
    : group?.genre
      ? [group.genre]
      : [];
  const decadeRaw = group?.decade;
  const decade =
    decadeRaw === "" || decadeRaw == null ? undefined : Number(decadeRaw);
  const theme = String(group?.theme || "").trim();
  const motif = String(group?.motif || "").trim();
  const rating = String(group?.content_rating || "").trim();
  const payload = {};
  if (genres.length) payload.genres = genres;
  if (Number.isFinite(decade)) payload.decade = decade;
  if (theme) payload.themes = [theme];
  if (motif) payload.motifs = [motif];
  if (rating) payload.content_ratings = [rating];
  return payload;
}

/** Serialize UI filter groups → API craft_filters (legacy flat or version 2). */
export function buildCraftFiltersPayload(craft) {
  const groups = Array.isArray(craft?.filter_groups)
    ? craft.filter_groups
    : null;
  if (groups) {
    const payloads = groups.map(payloadFromGroup).filter((p) => Object.keys(p).length);
    if (!payloads.length) return {};
    if (payloads.length === 1) return payloads[0];
    return { version: 2, groups: payloads };
  }
  // Legacy single-field draft shape (genre/decade/theme/content_rating on root).
  return payloadFromGroup(craft);
}

export function craftFiltersSummary(craftFilters) {
  const groups = filterGroupsFromCraftFilters(craftFilters);
  const labels = groups
    .filter(groupHasFilters)
    .map((g) => {
      const bits = [];
      if (g.genres?.[0]) bits.push(g.genres[0]);
      if (g.decade) bits.push(`${g.decade}s`);
      if (g.motif) bits.push(g.motif);
      if (g.theme) bits.push(g.theme);
      if (g.content_rating) bits.push(String(g.content_rating).toUpperCase());
      return bits.join(" ∩ ");
    })
    .filter(Boolean);
  if (!labels.length) return "";
  return labels.join("  OR  ");
}

/** Draft form state from status/station_meta for Settings read/write. */
export function craftDraftFromStation(station = {}) {
  const filters = station?.craft_filters || {};
  const filterGroups = filterGroupsFromCraftFilters(filters);
  const primary = filterGroups[0] || emptyFilterGroup();
  return {
    name: String(station?.name || "").trim(),
    media_scope: station?.media_scope || "both",
    subtitles_enabled: Boolean(station?.subtitles_enabled),
    source: station?.source || "",
    motif: station?.motif || "",
    cluster_tag: station?.cluster_tag || "",
    collection_title: station?.collection_title || "",
    programming_mode: station?.programming_mode || "",
    filter_groups: filterGroups,
    // Convenience mirrors of primary group (tests + older callers).
    genres: primary.genres || [],
    decade: primary.decade ?? "",
    theme: primary.theme || "",
    content_rating: primary.content_rating || "",
  };
}

/** Empty craft form defaults including one blank filter group. */
export function emptyCraftDraft(overrides = {}) {
  return {
    name: "",
    number: "",
    source: "motif",
    programming_mode: "shuffle",
    media_scope: "both",
    motif: "",
    cluster_tag: "",
    collection_id: "",
    collection_title: "",
    youth_safe: false,
    filter_groups: [emptyFilterGroup()],
    genres: [],
    decade: "",
    theme: "",
    content_rating: "",
    ...overrides,
  };
}
