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

/** A movie still counts as "now starting" for this long after its start. */
export const LIVE_MOVIE_START_GRACE_SEC = 180;

/** Next title counts as "about to air" only inside this window. */
export const LIVE_MOVIE_IMMINENT_SEC = 180;

function programStartSec(program) {
  const start = Number(program?.start ?? program?.started_at);
  return Number.isFinite(start) ? start : null;
}

function asEpochSeconds(nowMs) {
  const raw = Number(nowMs);
  if (!Number.isFinite(raw)) return Date.now() / 1000;
  return raw > 1e12 ? raw / 1000 : raw;
}

/**
 * Positive movie signal from guide/OSD. Shows, episodes, and flex pads are not movies.
 * Unknown types skip — a bare title is not enough.
 * @param {object | null | undefined} program
 */
export function isLiveMovieProgram(program) {
  if (!program || typeof program !== "object") return false;
  if (program.is_flex || program.isFlex) return false;
  const kind = String(program.media_type || program.type || "").trim().toLowerCase();
  if (kind === "show" || kind === "episode" || kind === "tv" || kind === "series") return false;
  const episodeTitle = String(program.episode_title || "").trim();
  if (episodeTitle) return false;
  if (kind !== "movie" && kind !== "movies") return false;
  return Boolean(String(program.title || "").trim());
}

/**
 * The movie that is starting now or about to air, or null.
 * Mid-feature tunes and non-movies do not qualify.
 * @param {object | null | undefined} osd
 * @param {number} [nowMs]
 */
export function liveMovieComingOn(osd, nowMs = Date.now()) {
  if (!osd || typeof osd !== "object") return null;
  const nowSec = asEpochSeconds(nowMs);
  const nowProg = osd.isFlex ? null : osd.nowProgram;
  if (isLiveMovieProgram(nowProg)) {
    const start = programStartSec(nowProg);
    if (start != null) {
      const elapsed = nowSec - start;
      if (elapsed >= 0 && elapsed <= LIVE_MOVIE_START_GRACE_SEC) return nowProg;
      if (elapsed < 0 && -elapsed <= LIVE_MOVIE_IMMINENT_SEC) return nowProg;
    }
  }
  const nextProg = osd.nextProgram;
  if (!isLiveMovieProgram(nextProg)) return null;
  const nextStart = programStartSec({
    start: osd.nextStart ?? nextProg.start,
    started_at: nextProg.started_at,
  });
  if (nextStart == null) return null;
  const until = nextStart - nowSec;
  if (until >= 0 && until <= LIVE_MOVIE_IMMINENT_SEC) return nextProg;
  return null;
}

/**
 * Stable id for one movie arrival. Empty when Live should not request a bumper.
 * @param {object | null | undefined} osd
 * @param {number} [nowMs]
 */
export function livePrerollCueId(osd, nowMs = Date.now()) {
  const program = liveMovieComingOn(osd, nowMs);
  if (!program) return "";
  const start = programStartSec(program);
  const title = String(program.title || "").trim();
  return `${start ?? ""}:${title}`;
}

/**
 * Live requests a trailer only when {@link liveMovieComingOn} finds a movie.
 * @param {object | null | undefined} osd
 * @param {number} [nowMs]
 */
export function shouldPlayLivePreroll(osd, nowMs = Date.now()) {
  return liveMovieComingOn(osd, nowMs) != null;
}
