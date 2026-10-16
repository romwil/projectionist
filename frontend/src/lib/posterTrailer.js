/** Poster hover trailer lookup: play a key, or a toast when there isn't one. */

export const NO_TRAILER_TOAST = "No trailer for this title.";
export const TRAILER_REQUEST_FAILED_TOAST = "Couldn't load the trailer.";

/**
 * Path for the title-detail request the poster trailer control already uses.
 * `null` when the card has no identity to look up.
 * @param {Record<string, unknown> | null | undefined} item
 * @returns {string | null}
 */
export function posterTrailerRequestPath(item) {
  const mediaType = String(item?.media_type || "").trim();
  const tmdbId = item?.tmdb_id;
  const ratingKey = item?.rating_key;
  if (!mediaType || !(tmdbId || ratingKey)) return null;
  const id = tmdbId || ratingKey;
  const idType = tmdbId ? "tmdb" : "rating_key";
  return `/title/${mediaType}/${id}?id_type=${encodeURIComponent(idType)}&enrich=1`;
}

/**
 * @param {{ detail?: Record<string, unknown> | null, error?: { message?: string } | null }} [input]
 * @returns {{ loading: false, open: boolean, key: string, toast: string }}
 */
export function trailerLookupOutcome({ detail = null, error = null } = {}) {
  if (error) {
    const message = String(error.message || "").trim();
    return {
      loading: false,
      open: false,
      key: "",
      toast: message && message !== NO_TRAILER_TOAST ? message : TRAILER_REQUEST_FAILED_TOAST,
    };
  }
  const key = String(detail?.trailer_youtube_key || "").trim();
  if (key) {
    return { loading: false, open: true, key, toast: "" };
  }
  return { loading: false, open: false, key: "", toast: NO_TRAILER_TOAST };
}
