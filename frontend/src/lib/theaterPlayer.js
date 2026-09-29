/** Shared in-app theater helpers — skip zones, resume, progress, HLS attach. */

export const SKIP_SECONDS = 15;
export const RESUME_THRESHOLD_MS = 2 * 60 * 1000;
export const PROGRESS_THROTTLE_MS = 10_000;
export const DOUBLE_TAP_MS = 300;
export const OSD_IDLE_MS = 3200;

export function libraryWatchPath(ratingKey) {
  const key = String(ratingKey || "").trim();
  if (!key) return "";
  return `/watch/${encodeURIComponent(key)}`;
}

export function libraryWatchPopoutPath(ratingKey) {
  const path = libraryWatchPath(ratingKey);
  return path ? `${path}/popout` : "";
}

export function libraryWatchTo(ratingKey, fromLocation = null) {
  const pathname = libraryWatchPath(ratingKey);
  if (!pathname) return null;
  const from =
    typeof fromLocation?.state?.from === "string" && fromLocation.state.from.startsWith("/")
      ? fromLocation.state.from
      : `${fromLocation?.pathname || ""}${fromLocation?.search || ""}` || "/";
  return { pathname, state: { from } };
}

/** Left / right thirds skip; center is play/pause or fullscreen on double-activate. */
export function skipZoneFromClientX(clientX, width) {
  const w = Number(width);
  const x = Number(clientX);
  if (!Number.isFinite(w) || w <= 0 || !Number.isFinite(x)) return "center";
  const ratio = x / w;
  if (ratio < 1 / 3) return "left";
  if (ratio > 2 / 3) return "right";
  return "center";
}

export function skipDeltaForZone(zone) {
  if (zone === "left") return -SKIP_SECONDS;
  if (zone === "right") return SKIP_SECONDS;
  return 0;
}

export function shouldResumeFromOffset(viewOffsetMs) {
  const offset = Number(viewOffsetMs);
  return Number.isFinite(offset) && offset >= RESUME_THRESHOLD_MS;
}

export function shouldSendProgress(lastSentAt, now = Date.now()) {
  if (lastSentAt == null) return true;
  const prior = Number(lastSentAt);
  if (!Number.isFinite(prior)) return true;
  return now - prior >= PROGRESS_THROTTLE_MS;
}

export function formatClockMs(ms) {
  const total = Math.max(0, Math.floor(Number(ms) / 1000) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const mm = String(minutes).padStart(hours > 0 ? 2 : 1, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`;
}

export function bufferedRanges(video) {
  if (!video?.buffered) return [];
  const out = [];
  for (let i = 0; i < video.buffered.length; i += 1) {
    try {
      out.push({ start: video.buffered.start(i), end: video.buffered.end(i) });
    } catch {
      // Time ranges can throw while the buffer is mutating.
    }
  }
  return out;
}

export function isTheaterChromeTarget(target) {
  if (!target || typeof target.closest !== "function") return false;
  return Boolean(
    target.closest("button, a, input, [role='slider'], [data-theater-chrome='true']"),
  );
}

/**
 * Collapse a second tap/click inside DOUBLE_TAP_MS into onDouble; otherwise onSingle.
 * The completing click of a double must not fire play/pause.
 */
export function createStageGesture({ onSingle, onDouble, delay = DOUBLE_TAP_MS } = {}) {
  let timer = null;
  let lastAt = 0;
  function clear() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }
  function handle(event) {
    const now = Date.now();
    if (lastAt && now - lastAt <= delay) {
      clear();
      lastAt = 0;
      onDouble?.(event);
      return;
    }
    lastAt = now;
    clear();
    timer = setTimeout(() => {
      timer = null;
      lastAt = 0;
      onSingle?.(event);
    }, delay);
  }
  handle.cancel = () => {
    clear();
    lastAt = 0;
  };
  return handle;
}

export function theaterHlsConfig() {
  return {
    enableWorker: false,
    lowLatencyMode: false,
    backBufferLength: 30,
    manifestLoadingTimeOut: 20000,
    levelLoadingTimeOut: 20000,
    fragLoadingTimeOut: 30000,
    xhrSetup: (xhr) => {
      xhr.withCredentials = true;
    },
  };
}

export function clampTime(seconds, duration) {
  const t = Number(seconds);
  const d = Number(duration);
  if (!Number.isFinite(t)) return 0;
  if (!Number.isFinite(d) || d <= 0) return Math.max(0, t);
  return Math.max(0, Math.min(d, t));
}

/**
 * Map a keydown key to a theater action.
 * Includes YouTube-style J/K/L and Minecraft-style A/S/D aliases (case-insensitive).
 * @returns {"toggle"|"skipBack"|"skipForward"|"mute"|"captions"|"fullscreen"|"escape"|null}
 */
export function theaterKeyAction(key) {
  const k = String(key ?? "");
  if (k === " " || k === "k" || k === "K" || k === "s" || k === "S") return "toggle";
  if (k === "j" || k === "J" || k === "a" || k === "A" || k === "ArrowLeft") return "skipBack";
  if (k === "l" || k === "L" || k === "d" || k === "D" || k === "ArrowRight") return "skipForward";
  if (k === "m" || k === "M") return "mute";
  if (k === "c" || k === "C") return "captions";
  if (k === "f" || k === "F") return "fullscreen";
  if (k === "Escape") return "escape";
  return null;
}

/**
 * Visibility lifecycle for VOD theater (`/watch`).
 *
 * Default product: keep playing through Mac Spaces / tab hide / brief focus loss.
 * Opt-in `pauseWhenBackgrounded` (uiPrefs, default false) soft-pauses on hide and
 * resumes when visible again if the user had been playing.
 * Real leave still uses pagehide / unmount stopSession — never kill the session
 * solely because visibility flipped to hidden.
 */
export function shouldPauseOnVisibilityHide({ pauseWhenBackgrounded, visibilityState }) {
  return Boolean(pauseWhenBackgrounded) && visibilityState === "hidden";
}

export function notePlayingBeforeHide({ playing, visibilityState }) {
  if (visibilityState !== "hidden") return null;
  return Boolean(playing);
}

export function shouldAutoResumePlayback({ wasPlaying, visibilityState }) {
  return visibilityState === "visible" && Boolean(wasPlaying);
}

/** True when local media is still attached and can try play() without re-arm. */
export function canResumeAttachedStream({ video, streamUrl } = {}) {
  const url = String(streamUrl || "").trim();
  if (!url) return false;
  if (!video) return false;
  return Boolean(video.currentSrc || video.src);
}
