/**
 * Client helpers for Projectionist preroll bumpers (independent per browser).
 */

/**
 * @param {unknown} payload
 * @returns {{ id: string, url: string, title: string, media_type: string } | null}
 */
export function normalizePrerollPayload(payload) {
  if (!payload || typeof payload !== "object") return null;
  const id = String(payload.id || "").trim();
  const url = String(payload.url || payload.stream_url || "").trim();
  if (!id || !url) return null;
  return {
    id,
    url,
    title: String(payload.title || "Preroll").trim() || "Preroll",
    media_type: String(payload.media_type || "video").trim() || "video",
  };
}

/**
 * Movies get a bumper; episodes skip unless force=true.
 * @param {{ media_type?: string } | null | undefined} session
 * @param {{ force?: boolean }} [options]
 */
export function shouldPlayMoviePreroll(session, { force = false } = {}) {
  if (force) return true;
  const kind = String(session?.media_type || "").toLowerCase();
  return kind === "movie";
}
