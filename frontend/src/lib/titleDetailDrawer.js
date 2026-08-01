import { titleDetailPath } from "./titleLinks.js";

/** Resolve drawer/API target from a library card or purge-candidate row. */
export function titleDetailTargetFromItem(item) {
  if (!item) return null;
  const mediaType = item.media_type === "show" ? "show" : "movie";
  if (item.tmdb_id) {
    return { mediaType, itemId: String(item.tmdb_id), idType: "tmdb" };
  }
  const ratingKey = String(item.rating_key || item.plex_rating_key || "").trim();
  if (ratingKey) {
    return { mediaType, itemId: ratingKey, idType: "rating_key" };
  }
  if (mediaType === "show" && item.tvdb_id) {
    return { mediaType, itemId: String(item.tvdb_id), idType: "tvdb" };
  }
  return null;
}

/** Alias for purge-candidate rows (same shape as library cards). */
export function titleDetailTargetFromPurgeCandidate(candidate) {
  return titleDetailTargetFromItem(candidate);
}

/** Build the full-page title detail route for a drawer target. */
export function titleDetailHrefFromTarget(target) {
  if (!target) return null;
  const { mediaType, itemId, idType } = target;
  return titleDetailPath({
    media_type: mediaType,
    tmdb_id: idType === "tmdb" ? itemId : null,
    rating_key: idType === "rating_key" ? itemId : null,
    tvdb_id: idType === "tvdb" ? itemId : null,
  });
}

/**
 * True when a click should open the in-place title overlay instead of navigating.
 * Modified clicks (new tab / new window) keep the full-page route.
 */
export function shouldOpenTitleOverlayClick(event) {
  if (!event || event.defaultPrevented) return false;
  if (typeof event.button === "number" && event.button !== 0) return false;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  return true;
}
