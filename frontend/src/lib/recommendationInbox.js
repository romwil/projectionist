function recommendationIdentity(item) {
  const type = item?.media_type === "show" ? "show" : "movie";
  const externalId = item?.tmdb_id || item?.tvdb_id || item?.rating_key || item?.plex_rating_key;
  return externalId ? `${type}:${externalId}` : `${type}:${String(item?.title || "").trim().toLowerCase()}:${item?.year || ""}`;
}

export function dedupeRecommendations(items = []) {
  const byIdentity = new Map();
  for (const item of items) {
    const key = recommendationIdentity(item);
    const current = byIdentity.get(key);
    // Retain the record with the richer sender note while preserving inbox order.
    if (!current || String(item?.message || "").length > String(current?.message || "").length) {
      byIdentity.set(key, item);
    }
  }
  return [...byIdentity.values()];
}

export function normalizeRecommendation(item) {
  return {
    ...item,
    // Recommendation payloads can omit in_library even when Plex supplied a
    // rating key. Keep an explicit false authoritative.
    in_library: item?.in_library ?? Boolean(item?.rating_key || item?.plex_rating_key),
  };
}
