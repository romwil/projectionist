import type {JsonObject, LibraryItem, JsParam} from "../api/types";
import {
  classifyLiveStreamHealth,
  stepLiveStreamHealthUi,
} from "./liveChannels.js";

/** Shared in-app theater helpers — skip zones, resume, progress, HLS attach. */

export const SKIP_SECONDS = 15;
/** Extra skip shown only when the Play bar is landscape and wide enough. */
export const SKIP_LONG_SECONDS = 30;
/** iPad-class landscape. Phone landscape stays on ±15 so the bar does not wrap over the slider. */
export const LONG_SKIP_MIN_WIDTH = 1000;
export const RESUME_THRESHOLD_MS = 2 * 60 * 1000;
export const PROGRESS_THROTTLE_MS = 10_000;
export const DOUBLE_TAP_MS = 300;
/** Library Play press-and-hold rate. Live TV must not set this. */
export const HOLD_PLAYBACK_RATE = 2;
export const OSD_IDLE_MS = 3200;
/** Collapse rapid Play scrub session-restarts into one seek. */
export const SEEK_RESTART_DEBOUNCE_MS = 280;
/**
 * How long a restarted Plex playlist may stay hidden before the seek fails.
 * The picture stays on the previous frame until a new video frame can paint.
 */
export const SEEK_PICTURE_TIMEOUT_MS = 12_000;
export const SEEK_FAILED_MESSAGE = "Couldn’t jump in this title.";

export function libraryWatchPath(ratingKey: string) {
  const key = String(ratingKey || "").trim();
  if (!key) return "";
  return `/watch/${encodeURIComponent(key)}`;
}

export function libraryWatchPopoutPath(ratingKey: string) {
  const path = libraryWatchPath(ratingKey);
  return path ? `${path}/popout` : "";
}

export function libraryWatchTo(ratingKey: string, fromLocation: JsParam = null) {
  const pathname = libraryWatchPath(ratingKey);
  if (!pathname) return null;
  const from =
    typeof fromLocation?.state?.from === "string" && fromLocation.state.from.startsWith("/")
      ? fromLocation.state.from
      : `${fromLocation?.pathname || ""}${fromLocation?.search || ""}` || "/";
  return { pathname, state: { from } };
}

/** Left / right thirds skip; center is play/pause or fullscreen on double-activate. */
export function skipZoneFromClientX(clientX: unknown, width: unknown) {
  const w = Number(width);
  const x = Number(clientX);
  if (!Number.isFinite(w) || w <= 0 || !Number.isFinite(x)) return "center";
  const ratio = x / w;
  if (ratio < 1 / 3) return "left";
  if (ratio > 2 / 3) return "right";
  return "center";
}

export function skipDeltaForZone(zone: JsParam) {
  if (zone === "left") return -SKIP_SECONDS;
  if (zone === "right") return SKIP_SECONDS;
  return 0;
}

/**
 * Bottom third of the picture only shows or hides the control overlay.
 * The rest of the picture keeps one-tap play/pause.
 * @returns {"osd"|"toggle"}
 */
export function pictureTapIntent(offsetY: unknown, height: unknown) {
  const y = Number(offsetY);
  const h = Number(height);
  if (!Number.isFinite(y) || !Number.isFinite(h) || h <= 0 || y < 0) return "toggle";
  if (y >= (h * 2) / 3) return "osd";
  return "toggle";
}

/** Apply a picture tap. Bottom third must not call pause/play. */
export function dispatchPictureTap({ offsetY, height, togglePlayback, toggleOsd }: JsParam = {}) {
  if (pictureTapIntent(offsetY, height) === "osd") {
    toggleOsd?.();
    return "osd";
  }
  togglePlayback?.();
  return "playback";
}

/**
 * Bottom-third result from the overlay state at pointerdown.
 * A reveal uses the same idle as every other show. A later tap hides.
 * The pointerdown snapshot matters: the click's own mousemove can reveal the
 * bar before the gesture delay fires, and that follow-up must not hide it.
 */
export function bottomThirdTapResult({ visibleAtPointerDown = false, idleMs = OSD_IDLE_MS }: JsParam = {}) {
  if (visibleAtPointerDown) return { effect: "hide", hideAfterMs: 0 };
  return { effect: "show", hideAfterMs: idleMs };
}

/** After the bar hides while paused, the center Play glyph stays one more idle. */
export function centerPlayHoldAfterOsdHide({ paused = false, idleMs = OSD_IDLE_MS }: JsParam = {}) {
  if (!paused) return { visible: false, hideAfterMs: 0 };
  return { visible: true, hideAfterMs: idleMs };
}

/** Close leaves the player from the bar. Back stays out of More. */
export function playerClosePlacement() {
  return { onBar: true, inMoreMenu: false, label: "Close" };
}

export function shouldResumeFromOffset(viewOffsetMs: number) {
  const offset = Number(viewOffsetMs);
  return Number.isFinite(offset) && offset >= RESUME_THRESHOLD_MS;
}

export function shouldSendProgress(lastSentAt: unknown, now: number = Date.now()) {
  if (lastSentAt == null) return true;
  const prior = Number(lastSentAt);
  if (!Number.isFinite(prior)) return true;
  return now - prior >= PROGRESS_THROTTLE_MS;
}

export function formatClockMs(ms: JsParam) {
  const total = Math.max(0, Math.floor(Number(ms) / 1000) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const mm = String(minutes).padStart(hours > 0 ? 2 : 1, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`;
}

export function bufferedRanges(video: JsParam) {
  if (!video?.buffered) return [];
  const out: JsParam[] = [];
  for (let i = 0; i < video.buffered.length; i += 1) {
    try {
      out.push({ start: video.buffered.start(i), end: video.buffered.end(i) });
    } catch {
      // Time ranges can throw while the buffer is mutating.
    }
  }
  return out;
}

export function isTheaterChromeTarget(target: JsParam) {
  if (!target || typeof target.closest !== "function") return false;
  return Boolean(target.closest("button, a, input, [role='slider'], [data-theater-chrome='true']"));
}

function theaterSelectionGetter(getSelection: JsParam) {
  if (typeof getSelection === "function") return getSelection;
  if (typeof window !== "undefined" && typeof window.getSelection === "function") {
    return () => window.getSelection();
  }
  return null;
}

/** Drop a Safari / iOS selection so the 2x chip and stage do not stay highlighted. */
export function clearTheaterTextSelection(getSelection?: JsParam) {
  const getter = theaterSelectionGetter(getSelection);
  if (!getter) return false;
  try {
    getter()?.removeAllRanges?.();
    return true;
  } catch {
    return false;
  }
}

/**
 * iPad Safari starts a system text-selection / callout on press-and-hold.
 * Call from stage pointerdown outside chrome. Never for scrubber or inputs.
 * @returns {boolean} true when preventDefault ran
 */
export function suppressHoldTextSelection(event: JsParam, { getSelection }: JsParam = {}) {
  if (!event || isTheaterChromeTarget(event.target)) return false;
  event.preventDefault?.();
  clearTheaterTextSelection(getSelection);
  return true;
}

/**
 * Collapse a second tap/click inside DOUBLE_TAP_MS into onDouble; otherwise onSingle.
 * The completing click of a double must not fire play/pause.
 */
export function createStageGesture({ onSingle, onDouble, delay = DOUBLE_TAP_MS }: JsParam = {}) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastAt = 0;
  function clear() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }
  function handle(event: JsParam) {
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

/**
 * Hold-to-2x: a press longer than the single-tap window must not pause on release.
 * Live TV must not call this — linear clock stays 1x.
 */
export function holdToRateShouldCancelTap(
  {
  downAtMs,
  upAtMs,
  delayMs = DOUBLE_TAP_MS,
}: JsParam = {},
) {
  const down = Number(downAtMs);
  const up = Number(upAtMs);
  const delay = Number(delayMs);
  if (!Number.isFinite(down) || !Number.isFinite(up) || !Number.isFinite(delay)) return false;
  return up - down >= delay;
}

/** Set playbackRate; return the rate the element actually reports. */
export function applyHoldPlaybackRate(video: JsParam, rate = HOLD_PLAYBACK_RATE) {
  if (!video) return 1;
  const next = Number(rate);
  if (!Number.isFinite(next) || next <= 0) return Number(video.playbackRate) || 1;
  try {
    video.playbackRate = next;
  } catch {
    // iPad Safari often ignores playbackRate on live-like Plex HLS.
  }
  return Number(video.playbackRate) || 1;
}

export function restoreHoldPlaybackRate(video: JsParam) {
  return applyHoldPlaybackRate(video, 1);
}

/** 2x chip only when the element actually doubled — never a fake badge. */
export function shouldShowHoldRateChip(playbackRate: JsParam) {
  return Number(playbackRate) === HOLD_PLAYBACK_RATE;
}

/** Library Play stall contract — same delay as Live so brief underruns do not flash. */
export function libraryBufferingHealth(input: JsParam = {}) {
  return classifyLiveStreamHealth(input);
}

export function stepLibraryBufferingUi(state: JsParam, input: JsParam) {
  return stepLiveStreamHealthUi(state, input);
}

/**
 * Obvious buffering OSD after the Live holdMs delay.
 * Hide when a current frame is present and we are no longer waiting.
 * Seek-fail copy owns the stage — do not fight it.
 */
export function shouldShowLibraryBufferingChip(
  {
  displayedHealth = "ok",
  hasError = false,
  seekFailed = false,
  readyState = 0,
  videoWidth = 0,
  waiting = false,
}: JsParam = {},
) {
  if (hasError || seekFailed) return false;
  if (displayedHealth !== "buffering" && displayedHealth !== "stalled") return false;
  if (!waiting && Number(readyState) >= 2 && Number(videoWidth) > 0) return false;
  return true;
}

export function libraryBufferingCopy(health: JsParam) {
  if (health === "stalled") return "Still waiting for this title…";
  if (health === "buffering") return "Buffering";
  return "";
}

export function theaterHlsConfig() {
  return {
    enableWorker: false,
    lowLatencyMode: false,
    backBufferLength: 30,
    manifestLoadingTimeOut: 20000,
    levelLoadingTimeOut: 20000,
    fragLoadingTimeOut: 30000,
    // Projectionist draws soft tracks itself. Do not fetch playlist WebVTT
    // (often a Plex overlay URL that 404s and can stall Live).
    renderTextTracksNatively: false,
    enableWebVTT: false,
    enableIMSC1: false,
    xhrSetup: (xhr: JsParam) => {
      xhr.withCredentials = true;
    },
  };
}

export function clampTime(seconds: unknown, duration: unknown) {
  const t = Number(seconds);
  const d = Number(duration);
  if (!Number.isFinite(t)) return 0;
  if (!Number.isFinite(d) || d <= 0) return Math.max(0, t);
  return Math.max(0, Math.min(d, t));
}

/** Range scrubber uses 0…SCRUB_MAX so the thumb has fine resolution. */
export const SCRUB_MAX = 1000;

/** Map playback position → controlled range value (0…SCRUB_MAX). */
export function scrubPctFromMs(nowMs: unknown, durationMs: number) {
  const d = Number(durationMs);
  if (!Number.isFinite(d) || d <= 0) return 0;
  const t = Number(nowMs);
  if (!Number.isFinite(t) || t <= 0) return 0;
  return Math.max(0, Math.min(SCRUB_MAX, Math.round((t / d) * SCRUB_MAX)));
}

/** Map range value (0…SCRUB_MAX) → seek offset in ms. */
export function msFromScrubPct(pct: JsParam, durationMs: number) {
  const d = Number(durationMs);
  if (!Number.isFinite(d) || d <= 0) return 0;
  const p = Number(pct);
  if (!Number.isFinite(p)) return 0;
  return Math.round((Math.max(0, Math.min(SCRUB_MAX, p)) / SCRUB_MAX) * d);
}

/**
 * True when ±30 skip buttons fit the Play bar: landscape and at least iPad width.
 * Portrait and phone landscape stay on ±15.
 */
export function longSkipFits(viewport: JsParam) {
  const width = Number(viewport?.width);
  const height = Number(viewport?.height);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return false;
  return width > height && width >= LONG_SKIP_MIN_WIDTH;
}

/**
 * Coalesce a Play scrubber gesture into one seek.
 * iPad Safari emits a burst of `input` events while the finger moves. Seeking
 * on each event restarts the HLS session and the player locks. Preview during
 * the burst; commit once on release, or once after the burst goes quiet if
 * pointerup never arrives.
 */
export function createScrubCommit({ onCommit, quietMs = 180, lostEndMs = 700 }: JsParam = {}) {
  let dragging = false;
  let latest: JsParam = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function clearTimer() {
    if (timer != null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function commit() {
    clearTimer();
    dragging = false;
    if (latest == null) return;
    const pct = latest;
    latest = null;
    onCommit?.(pct);
  }

  return {
    begin() {
      dragging = true;
      clearTimer();
    },
    input(pct: JsParam) {
      const n = Number(pct);
      if (!Number.isFinite(n)) return;
      latest = n;
      clearTimer();
      timer = setTimeout(commit, dragging ? lostEndMs : quietMs);
    },
    end() {
      commit();
    },
    cancel() {
      clearTimer();
      dragging = false;
      latest = null;
    },
    isDragging() {
      return dragging;
    },
  };
}

/**
 * Prefer a local HTMLMediaElement seek when the target is already buffered;
 * otherwise the caller should restart the Plex VOD session at offsetMs.
 * Live theater has no scrubber (live-edge only) — this is library `/watch` only.
 */
export function canLocalSeekTo(video: JsParam, offsetSeconds: unknown) {
  const target = Number(offsetSeconds);
  if (!video || !Number.isFinite(target)) return false;
  return bufferedRanges(video).some((range) => target >= (range as JsParam).start && target <= (range as JsParam).end);
}

/**
 * Plex seek keeps the same proxy playlist URL and restarts the transcoder.
 * Bump `seekEpoch` so the player tears down the old MediaSource and loads the
 * new session. Epoch 0 leaves the URL untouched (first play).
 */
export function playbackSrcForSeek(streamUrl: JsParam, seekEpoch = 0) {
  const url = String(streamUrl || "").trim();
  const epoch = Number(seekEpoch) || 0;
  if (!url || epoch <= 0) return url;
  const hashAt = url.indexOf("#");
  const hash = hashAt >= 0 ? url.slice(hashAt) : "";
  const base = hashAt >= 0 ? url.slice(0, hashAt) : url;
  const join = base.includes("?") ? "&" : "?";
  return `${base}${join}seek=${encodeURIComponent(String(Math.floor(epoch)))}${hash}`;
}

/**
 * While a session-restart seek is in flight, the video element must stay
 * hidden. A decoded snow frame still has a width — only a real, current
 * frame (HAVE_CURRENT_DATA and a non-zero video width) may be shown.
 * Outside a seek hold the picture is always presentable.
 */
export function shouldRevealPlaybackPicture(
  {
  holdingSeek = false,
  readyState = 0,
  videoWidth = 0,
}: JsParam = {},
) {
  if (!holdingSeek) return true;
  const ready = Number(readyState);
  const width = Number(videoWidth);
  return Number.isFinite(ready) && ready >= 2 && Number.isFinite(width) && width > 0;
}

/**
 * Decide whether the reloaded playlist timeline is 0-based or already at the
 * Plex offset (copyts). Sample once when the new picture is ready.
 * Returns milliseconds to add to `video.currentTime`.
 */
export function seekTimelineOriginMs({ currentTimeSec, committedOffsetMs }: JsParam = {}) {
  const mediaMs = Math.max(0, Math.round((Number(currentTimeSec) || 0) * 1000));
  const committed = Math.max(0, Math.round(Number(committedOffsetMs) || 0));
  if (committed > 1500 && mediaMs + 1500 < committed) return committed;
  return 0;
}

/** Playhead after a seek, including a 0-based transcoder timeline. */
export function playheadMsFromMedia({ currentTimeSec, originMs = 0 }: JsParam = {}) {
  const mediaMs = Math.max(0, Math.round((Number(currentTimeSec) || 0) * 1000));
  const origin = Math.max(0, Math.round(Number(originMs) || 0));
  return mediaMs + origin;
}

/**
 * Freeze the last painted frame to cover the element while the next playlist
 * loads. Returns "" when there is nothing safe to draw (tests, empty video).
 */
export function capturePlaybackHoldFrame(video: JsParam) {
  const width = Number(video?.videoWidth) || 0;
  const height = Number(video?.videoHeight) || 0;
  if (!video || width < 2 || height < 2) return "";
  if (typeof document === "undefined" || typeof document.createElement !== "function") return "";
  try {
    const canvas = document.createElement("canvas");
    const maxW = 960;
    const w = Math.min(width, maxW);
    const h = Math.max(1, Math.round(height * (w / width)));
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return "";
    ctx.drawImage(video, 0, 0, w, h);
    return canvas.toDataURL("image/jpeg", 0.72);
  } catch {
    return "";
  }
}

/**
 * Map a keydown key to a theater action.
 * Includes YouTube-style J/K/L, Minecraft-style A/S/D (case-insensitive),
 * ArrowLeft/ArrowRight (±SKIP_SECONDS, same as the −15/+15 buttons), and Space.
 * @returns {"toggle"|"skipBack"|"skipForward"|"mute"|"captions"|"fullscreen"|"escape"|null}
 */
export function theaterKeyAction(key: string) {
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

/** True while the user is typing — library Play shortcuts must not steal those keys. */
export function isPlayShortcutBlockedTarget(target: JsParam) {
  if (!target || typeof target !== "object") return false;
  const tag = String(target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  return Boolean(target.isContentEditable);
}

/**
 * Library `/watch` transport keys. Calls the same `skipBy` as the on-screen
 * −15/+15 buttons (ArrowLeft/A/J back, ArrowRight/D/L forward) and the same
 * toggle as the Pause/Play button (Space/S/K). Does not touch ±30.
 * Scrubber range inputs are blocked so Left/Right keep native slider behavior.
 * Returns true when the event was consumed (including Space key-repeat, which
 * is swallowed so the page does not scroll).
 */
export function dispatchLibraryPlayKey(event: JsParam, { skipBy, togglePlayback }: JsParam = {}) {
  if (!event || isPlayShortcutBlockedTarget(event.target)) return false;
  const action = theaterKeyAction(event.key);
  if (action !== "toggle" && action !== "skipBack" && action !== "skipForward") return false;
  event.preventDefault?.();
  if (event.repeat && action === "toggle") return true;
  if (action === "toggle") togglePlayback?.();
  else if (action === "skipBack") skipBy?.(-SKIP_SECONDS);
  else skipBy?.(SKIP_SECONDS);
  return true;
}

/**
 * Visibility lifecycle for VOD theater (`/watch`).
 *
 * Default product: keep playing through Mac Spaces / tab hide / brief focus loss.
 * Opt-in `pauseWhenBackgrounded` (uiPrefs, default false) soft-pauses on hide and
 * resumes when visible again if the user had been playing.
 * Real leave still uses pagehide / unmount stopSession — never kill the session
 * solely because visibility flipped to hidden.
 *
 * iPad Safari often fires `pagehide` when locking the screen or switching apps.
 * When `event.persisted` is true (bfcache), keep the session so `pageshow` can
 * resume open→resume→done without re-arming from zero.
 */
export function shouldPauseOnVisibilityHide({ pauseWhenBackgrounded, visibilityState }: JsParam) {
  return Boolean(pauseWhenBackgrounded) && visibilityState === "hidden";
}

export function notePlayingBeforeHide({ playing, visibilityState }: JsParam) {
  if (visibilityState !== "hidden") return null;
  return Boolean(playing);
}

export function shouldAutoResumePlayback({ wasPlaying, visibilityState }: JsParam) {
  return visibilityState === "visible" && Boolean(wasPlaying);
}

/** True when pagehide means a real unload (not bfcache / soft background). */
export function shouldStopSessionOnPageHide({ persisted = false }: JsParam = {}) {
  return !persisted;
}

/** True when pageshow should try to continue after a bfcache restore. */
export function shouldResumeOnPageShow({ persisted = false, wasPlaying = false }: JsParam = {}) {
  return Boolean(persisted) && Boolean(wasPlaying);
}

/** True when local media is still attached and can try play() without re-arm. */
export function canResumeAttachedStream({ video, streamUrl }: JsParam = {}) {
  const url = String(streamUrl || "").trim();
  if (!url) return false;
  if (!video) return false;
  return Boolean(video.currentSrc || video.src);
}

/** Library Play letterbox: default art (blurred poster), or a black frame. */
export function playStageChrome(blackFrame = false) {
  const black = Boolean(blackFrame);
  return {
    className: black ? "theater-player--black-frame" : "",
    dataPlayFrame: black ? "black" : "art",
    hidePoster: black,
  };
}

/** True when the document (or webkit) reports an active fullscreen element. */
export function isDocumentFullscreen() {
  if (typeof document === "undefined") return false;
  return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
}

/** iPhone / iPad / iPod, including iPadOS desktop-class UA. */
export function isIosSafariUserAgent(userAgent = "", { maxTouchPoints }: JsParam = {}) {
  const ua = String(userAgent || "");
  if (/iPad|iPhone|iPod/i.test(ua)) return true;
  const touches = Number(
    maxTouchPoints ?? (typeof navigator !== "undefined" ? navigator.maxTouchPoints : 0),
  );
  return /Macintosh/i.test(ua) && Number.isFinite(touches) && touches > 1;
}

/**
 * iOS Safari does not fullscreen a div the way desktop does. Use the media
 * element's webkitEnterFullscreen when the UA and the video both support it.
 */
export function shouldUseWebkitVideoFullscreen(video: JsParam, { userAgent, maxTouchPoints }: JsParam = {}) {
  if (!video || typeof video.webkitEnterFullscreen !== "function") return false;
  if (video.webkitSupportsFullscreen === false) return false;
  const ua = userAgent ?? (typeof navigator !== "undefined" ? navigator.userAgent : "");
  return isIosSafariUserAgent(ua, { maxTouchPoints });
}

function exitWebkitVideoFullscreen(video: JsParam) {
  const exit = video?.webkitExitFullscreen || video?.webkitEndFullscreen;
  if (typeof exit !== "function") return false;
  try {
    exit.call(video);
    return true;
  } catch {
    return false;
  }
}

/**
 * Enter/exit theater fullscreen. On iPhone Safari, `requestFullscreen` on the
 * shell is a no-op (watch is already a fixed viewport) — call
 * `video.webkitEnterFullscreen` from the user gesture instead. Desktop still
 * prefers element fullscreen so custom OSD stays. CSS immersive remains the
 * last fallback when neither API exists.
 * @returns {"exit"|"enter"|"webkit"|"immersive"|"noop"}
 */
export function toggleTheaterFullscreen(root: JsParam,
  { immersiveClass = "theater-player--immersive", video = null, userAgent, maxTouchPoints }: JsParam = {},
) {
  if (!root && !video) return "noop";
  const hasDocument = typeof document !== "undefined";
  const immersive = Boolean(immersiveClass && root?.classList?.contains?.(immersiveClass));
  const webkitOpts = { userAgent, maxTouchPoints };

  if (video?.webkitDisplayingFullscreen) {
    exitWebkitVideoFullscreen(video);
    if (immersiveClass) root?.classList?.remove?.(immersiveClass);
    return "exit";
  }

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
    if (immersiveClass) root?.classList?.remove?.(immersiveClass);
    return "exit";
  }

  if (immersive && immersiveClass && root) {
    root.classList.remove(immersiveClass);
    return "exit";
  }

  if (shouldUseWebkitVideoFullscreen(video, webkitOpts)) {
    try {
      video.webkitEnterFullscreen();
      return "webkit";
    } catch {
      // Fall through to element fullscreen / CSS immersive.
    }
  }

  const request =
    typeof root?.requestFullscreen === "function"
      ? () => root.requestFullscreen()
      : typeof root?.webkitRequestFullscreen === "function"
        ? () => root.webkitRequestFullscreen()
        : null;
  if (request) {
    try {
      const result = request();
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

  if (immersiveClass && root) {
    root.classList?.add?.(immersiveClass);
    return "immersive";
  }
  return "noop";
}

/** Shown on the end card when the series has no later episode in the library. */
export const NEXT_EPISODE_MISSING_MESSAGE = "That’s the last episode in your library.";

/** Shown on the end card when Next Episode cannot open the watch route. */
export const NEXT_EPISODE_UNAVAILABLE_MESSAGE = "Couldn’t start the next episode.";

function episodePlayRatingKey(item: LibraryItem | null | undefined) {
  return String(item?.play_rating_key || item?.rating_key || item?.plex_rating_key || "").trim();
}

/**
 * Decide what the end-card Next Episode control should do.
 * `play` opens the in-app watch route. `message` is a visible failure, never a no-op.
 * @returns {{ action: "play", path: string, ratingKey: string } | { action: "message", message: string }}
 */
export function nextEpisodeEndCardAction(next: JsParam, currentRatingKey = "") {
  const ratingKey = episodePlayRatingKey(next);
  const path = libraryWatchPath(ratingKey);
  if (!path) {
    return { action: "message", message: NEXT_EPISODE_MISSING_MESSAGE };
  }
  const currentPath = libraryWatchPath(currentRatingKey);
  if (currentPath && path === currentPath) {
    return { action: "message", message: NEXT_EPISODE_UNAVAILABLE_MESSAGE };
  }
  return { action: "play", path, ratingKey };
}

/**
 * Run the end-card Next Episode control.
 * Plays via `navigate(watchPath)` or surfaces `onMessage` when playback cannot start.
 */
export function runNextEpisodeEndCard(next: JsParam, currentRatingKey = "", { navigate, onMessage }: JsParam = {}) {
  const decision = nextEpisodeEndCardAction(next, currentRatingKey);
  if (decision.action === "play") {
    if (typeof navigate === "function") navigate(decision.path);
    return decision;
  }
  if (typeof onMessage === "function") onMessage(decision.message);
  return decision;
}

/** In-app Explore route. End card uses this to leave the player. */
export const EXPLORE_PATH = "/explore";

/**
 * Leave the end card for Explore. Independent of whether Next Episode can play.
 * @returns {{ action: "explore", path: string }}
 */
export function runEndCardBackToExplore({ navigate }: JsParam = {}) {
  if (typeof navigate === "function") navigate(EXPLORE_PATH);
  return { action: "explore", path: EXPLORE_PATH };
}
