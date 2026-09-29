/** Shared in-app theater helpers — skip zones, resume, progress, HLS attach. */

export const SKIP_SECONDS = 15;
export const RESUME_THRESHOLD_MS = 2 * 60 * 1000;
export const PROGRESS_THROTTLE_MS = 10_000;
export const DOUBLE_TAP_MS = 300;
export const OSD_IDLE_MS = 3200;
/** Collapse rapid Play scrub session-restarts into one seek. */
export const SEEK_RESTART_DEBOUNCE_MS = 280;

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

/** Range scrubber uses 0…SCRUB_MAX so the thumb has fine resolution. */
export const SCRUB_MAX = 1000;

/** Map playback position → controlled range value (0…SCRUB_MAX). */
export function scrubPctFromMs(nowMs, durationMs) {
  const d = Number(durationMs);
  if (!Number.isFinite(d) || d <= 0) return 0;
  const t = Number(nowMs);
  if (!Number.isFinite(t) || t <= 0) return 0;
  return Math.max(0, Math.min(SCRUB_MAX, Math.round((t / d) * SCRUB_MAX)));
}

/** Map range value (0…SCRUB_MAX) → seek offset in ms. */
export function msFromScrubPct(pct, durationMs) {
  const d = Number(durationMs);
  if (!Number.isFinite(d) || d <= 0) return 0;
  const p = Number(pct);
  if (!Number.isFinite(p)) return 0;
  return Math.round((Math.max(0, Math.min(SCRUB_MAX, p)) / SCRUB_MAX) * d);
}

/**
 * Prefer a local HTMLMediaElement seek when the target is already buffered;
 * otherwise the caller should restart the Plex VOD session at offsetMs.
 * Live theater has no scrubber (live-edge only) — this is library `/watch` only.
 */
export function canLocalSeekTo(video, offsetSeconds) {
  const target = Number(offsetSeconds);
  if (!video || !Number.isFinite(target)) return false;
  return bufferedRanges(video).some((range) => target >= range.start && target <= range.end);
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

/** True when the document (or webkit) reports an active fullscreen element. */
export function isDocumentFullscreen() {
  if (typeof document === "undefined") return false;
  return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
}

/**
 * Enter/exit theater fullscreen on the shell that owns video + OSD.
 * iOS Safari often rejects element Fullscreen API — fall back to a CSS
 * immersive class on the root. Prefer that over `video.webkitEnterFullscreen`,
 * which would hide custom OSD controls.
 * @returns {"exit"|"enter"|"immersive"|"noop"}
 */
export function toggleTheaterFullscreen(root, { immersiveClass = "theater-player--immersive" } = {}) {
  if (!root) return "noop";
  const hasDocument = typeof document !== "undefined";
  const immersive = Boolean(immersiveClass && root.classList?.contains?.(immersiveClass));

  if (hasDocument && isDocumentFullscreen()) {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (typeof exit === "function") {
      try {
        const result = exit.call(document);
        if (result?.catch) result.catch(() => {});
      } catch {
        // ignore
      }
    }
    if (immersiveClass) root.classList?.remove?.(immersiveClass);
    return "exit";
  }

  if (immersive && immersiveClass) {
    root.classList.remove(immersiveClass);
    return "exit";
  }

  const request = root.requestFullscreen || root.webkitRequestFullscreen;
  if (hasDocument && typeof request === "function") {
    try {
      const result = request.call(root);
      if (result?.then) {
        result.catch(() => {
          if (immersiveClass) root.classList?.add?.(immersiveClass);
        });
        return "enter";
      }
      return "enter";
    } catch {
      if (immersiveClass) {
        root.classList?.add?.(immersiveClass);
        return "immersive";
      }
    }
  }

  if (immersiveClass) {
    root.classList?.add?.(immersiveClass);
    return "immersive";
  }
  return "noop";
}

