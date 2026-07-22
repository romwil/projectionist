/** Build the in-app title detail route for a card/item, or null if not linkable. */
export function titleDetailPath(item) {
  if (!item) return null;
  const mediaType = item.media_type === "show" ? "show" : "movie";
  if (item.tmdb_id) {
    return `/title/${mediaType}/${item.tmdb_id}`;
  }
  const ratingKey = item.rating_key || item.plex_rating_key;
  if (ratingKey) {
    return `/title/${mediaType}/${encodeURIComponent(ratingKey)}?id_type=rating_key`;
  }
  if (mediaType === "show" && item.tvdb_id) {
    return `/title/${mediaType}/${item.tvdb_id}?id_type=tvdb`;
  }
  return null;
}

/**
 * Plex web deep link for a library title.
 * Requires rating_key; machineId makes the link open the correct server.
 */
export function plexWatchUrl(ratingKey, machineId = "") {
  const key = String(ratingKey || "").trim();
  if (!key) return "";
  const metadataKey = encodeURIComponent(`/library/metadata/${key}`);
  const server = String(machineId || "").trim();
  if (server) {
    return `https://app.plex.tv/desktop/#!/server/${encodeURIComponent(server)}/details?key=${metadataKey}`;
  }
  return "";
}

/** True when a card should offer a Watch on Plex action. */
export function canWatchOnPlex(item) {
  const playKey = String(item?.play_rating_key || item?.rating_key || "").trim();
  return Boolean(item?.in_library && playKey);
}

/** Prefer play_rating_key (episode resume) when present, else library rating_key. */
export function plexPlayRatingKey(item) {
  return String(item?.play_rating_key || item?.rating_key || item?.plex_rating_key || "").trim();
}
