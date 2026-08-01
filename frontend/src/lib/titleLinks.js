import { returnStateFromLocation } from "./backNav.js";

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
 * React Router `to` for full-page title detail, carrying return context so
 * BackLink can label/href the origin when bookmarks / modified clicks navigate.
 *
 * @param {Record<string, unknown> | null | undefined} item
 * @param {{ pathname?: string, search?: string, state?: { from?: string } } | null} fromLocation
 */
export function titleDetailTo(item, fromLocation = null) {
  const path = titleDetailPath(item);
  if (!path) return null;
  const qIndex = path.indexOf("?");
  const pathname = qIndex >= 0 ? path.slice(0, qIndex) : path;
  const search = qIndex >= 0 ? path.slice(qIndex) : "";
  return {
    pathname,
    search,
    state: returnStateFromLocation(fromLocation),
  };
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

/**
 * Plex web deep link for Live TV (household watch surface for Live Channels).
 * machineId prefers the correct server; without it, open the generic Live TV hub.
 */
export function plexLiveTvUrl(machineId = "") {
  const server = String(machineId || "").trim();
  if (server) {
    return `https://app.plex.tv/desktop/#!/server/${encodeURIComponent(server)}/live-tv`;
  }
  return "https://app.plex.tv/desktop/#!/live-tv";
}
