/**
 * Client helpers for Projectionist preroll bumpers (independent per browser).
 */

import { isLivePrerollAssetUrl, tryPlayLiveVideo } from "./liveChannels.js";
import type {JsonObject, JsParam} from "../api/types";

export { isLivePrerollAssetUrl };

export const PREROLL_TAP_COPY = "Tap the picture to start the bumper.";
/** Give autoplay / metadata this long, then skip rather than freeze the theater. */
export const BUMPER_PLAY_TIMEOUT_MS = 6000;
/** Playing but stuck on frame 0 — skip instead of a dead first-frame hang. */
export const BUMPER_FIRST_FRAME_STALL_MS = 4000;

export type BumperWatchDecision = "keep" | "watch" | "wait" | "gesture" | "skip";
export type BumperPlayGate = "start" | "ignore";
export type BumperPlaySettleAction = "playing" | "skip" | "gesture" | "ignore";

/**
 * Race a play() promise so a hung autoplay cannot pin Live on the first frame.
 * @param {Promise<unknown>} playPromise
 * @param {number} [timeoutMs]
 */
export function promiseWithTimeout(playPromise: Promise<unknown>, timeoutMs = BUMPER_PLAY_TIMEOUT_MS) {
  const ms = Number(timeoutMs);
  if (!Number.isFinite(ms) || ms <= 0) return playPromise;
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve("timeout"), ms);
    Promise.resolve(playPromise).then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      () => {
        clearTimeout(timer);
        resolve("timeout");
      },
    );
  });
}

/**
 * Keep a bumper that is actually moving. Skip a freeze, error, or hung play.
 * Autoplay-blocked stays on the tap overlay until the timeout, then skips.
 */
export function bumperWatchDecision({
  playResult = "idle",
  currentTime = 0,
  error = false,
  elapsedMs = 0,
  playTimeoutMs = BUMPER_PLAY_TIMEOUT_MS,
  stallMs = BUMPER_FIRST_FRAME_STALL_MS,
}: JsParam = {}): BumperWatchDecision {
  if (error) return "skip";
  const time = Number(currentTime);
  const elapsed = Number(elapsedMs);
  const timeout = Number(playTimeoutMs);
  const stall = Number(stallMs);
  if (playResult === "playing") {
    if (Number.isFinite(time) && time >= 0.2) return "keep";
    if (Number.isFinite(elapsed) && Number.isFinite(stall) && elapsed >= stall) return "skip";
    return "watch";
  }
  if (playResult === "ready") {
    if (Number.isFinite(elapsed) && Number.isFinite(timeout) && elapsed >= timeout) return "skip";
    return "gesture";
  }
  if (Number.isFinite(elapsed) && Number.isFinite(timeout) && elapsed >= timeout) return "skip";
  return "wait";
}

/**
 * loadeddata and canplay both call onReady. playResult stays idle until
 * playBumperVideo settles, so the second event must not start another play().
 */
export function bumperReadyPlayGate({
  cancelled = false,
  playResult = "idle",
  playInFlight = false,
}: JsParam = {}): BumperPlayGate {
  if (cancelled || playInFlight) return "ignore";
  if (playResult !== "idle") return "ignore";
  return "start";
}

/**
 * Settle one playBumperVideo attempt. A later timeout or overlapping autoplay
 * rejection must not skip a bumper that already reached playing.
 */
export function bumperPlaySettle({
  cancelled = false,
  result = "idle",
  playResult = "idle",
  videoPlaying = false,
}: JsParam = {}): BumperPlaySettleAction {
  if (cancelled) return "ignore";
  if (playResult === "playing" || result === "playing" || videoPlaying) return "playing";
  if (result === "idle") return "skip";
  return "gesture";
}

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
export async function playBumperVideo(video: JsParam, { timeoutMs = BUMPER_PLAY_TIMEOUT_MS }: JsParam = {}) {
  if (!video) return "idle";
  const result = await promiseWithTimeout(tryPlayLiveVideo(video), timeoutMs);
  return result === "timeout" ? "idle" : result;
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
