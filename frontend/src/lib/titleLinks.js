import { returnStateFromLocation } from "./backNav.js";
import { isPhonePlayViewport } from "./chatLayout.js";

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
 * Plex client deep link — phone Play should open the Plex app, not desktop web.
 */
export function plexClientPlayUrl(ratingKey, machineId = "") {
  const key = String(ratingKey || "").trim();
  const server = String(machineId || "").trim();
  if (!key || !server) return "";
  const metadataKey = encodeURIComponent(`/library/metadata/${key}`);
  return `plex://preplay/?metadataKey=${metadataKey}&server=${encodeURIComponent(server)}`;
}

/**
 * Plex web deep link for a library title.
 * Requires rating_key; machineId makes the link open the correct server.
 * On a 390-wide phone, prefer the Plex client scheme unless `toClient` is false.
 */
export function plexWatchUrl(ratingKey, machineId = "", options = {}) {
  const key = String(ratingKey || "").trim();
  if (!key) return "";
  const server = String(machineId || "").trim();
  if (!server) return "";
  const toClient = options.toClient ?? isPhonePlayViewport(options.viewportWidth);
  if (toClient) return plexClientPlayUrl(key, server);
  const metadataKey = encodeURIComponent(`/library/metadata/${key}`);
  return `https://app.plex.tv/desktop/#!/server/${encodeURIComponent(server)}/details?key=${metadataKey}`;
}

/** Rewrite a desktop Plex href to the client scheme on phone viewports. */
export function preferPhonePlexPlayHref(href, { viewportWidth, machineId } = {}) {
  const url = String(href || "").trim();
  if (!url || !isPhonePlayViewport(viewportWidth)) return url;
  if (url.startsWith("plex://")) return url;
  const keyMatch = url.match(/metadata%2F([^&]+)|\/metadata\/([^/?&]+)/i);
  const key = decodeURIComponent(keyMatch?.[1] || keyMatch?.[2] || "");
  const serverMatch = url.match(/\/server\/([^/]+)\//);
  const server = decodeURIComponent(serverMatch?.[1] || "") || String(machineId || "").trim();
  return plexClientPlayUrl(key, server) || url;
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
