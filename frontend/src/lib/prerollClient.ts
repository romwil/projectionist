/**
 * Client helpers for Projectionist preroll bumpers (independent per browser).
 */

import { tryPlayLiveVideo } from "./liveChannels.js";
import type {JsonObject, JsParam} from "../api/types";

export const PREROLL_TAP_COPY = "Tap the picture to start the bumper.";

/**
 * @param {unknown} payload
 * @returns {{ id: string, url: string, title: string, media_type: string } | null}
 */
export function normalizePrerollPayload(payload: JsParam) {
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
export function shouldPlayMoviePreroll(session: JsParam, { force = false }: JsParam = {}) {
  if (force) return true;
  const kind = String(session?.media_type || "").toLowerCase();
  return kind === "movie";
}

/** A movie still counts as "now starting" for this long after its start. */
export const LIVE_MOVIE_START_GRACE_SEC = 180;

/** Next title counts as "about to air" only inside this window. */
export const LIVE_MOVIE_IMMINENT_SEC = 180;

function programStartSec(program: JsParam) {
  const start = Number(program?.start ?? program?.started_at);
  return Number.isFinite(start) ? start : null;
}

function asEpochSeconds(nowMs: unknown) {
  const raw = Number(nowMs);
  if (!Number.isFinite(raw)) return Date.now() / 1000;
  return raw > 1e12 ? raw / 1000 : raw;
}

/**
 * Positive movie signal from guide/OSD. Shows, episodes, and flex pads are not movies.
 * Unknown types skip — a bare title is not enough.
 * @param {object | null | undefined} program
 */
export function isLiveMovieProgram(program: JsParam) {
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
 * The movie that is starting now, or null.
 * Flex pads and mid-feature tunes do not qualify — preroll is not the flex
 * gap source, and “up next in a few minutes” is still the pad.
 * @param {object | null | undefined} osd
 * @param {number} [nowMs]
 */
export function liveMovieComingOn(osd: JsParam, nowMs = Date.now()) {
  if (!osd || typeof osd !== "object") return null;
  if (osd.isFlex) return null;
  const nowSec = asEpochSeconds(nowMs);
  const nowProg = osd.nowProgram;
  if (!isLiveMovieProgram(nowProg)) return null;
  const start = programStartSec(nowProg);
  if (start == null) return null;
  const elapsed = nowSec - start;
  if (elapsed >= 0 && elapsed <= LIVE_MOVIE_START_GRACE_SEC) return nowProg;
  if (elapsed < 0 && -elapsed <= LIVE_MOVIE_IMMINENT_SEC) return nowProg;
  return null;
}

/**
 * Start (or gesture-retry) a preroll bumper. Muted-first, then unmute — the
 * same Live program audio contract as Watch. A blocked unmuted play is not a
 * no-op: the overlay tap calls this again so `video.play()` actually runs.
 * @param {HTMLMediaElement|null|undefined} video
 * @returns {Promise<"playing"|"ready"|"idle">}
 */
export async function playBumperVideo(video: JsParam) {
  return tryPlayLiveVideo(video);
}

/**
 * Stable id for one movie arrival. Empty when Live should not request a bumper.
 * @param {object | null | undefined} osd
 * @param {number} [nowMs]
 */
export function livePrerollCueId(osd: JsParam, nowMs = Date.now()) {
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
export function shouldPlayLivePreroll(osd: JsParam, nowMs = Date.now()) {
  return liveMovieComingOn(osd, nowMs) != null;
}
