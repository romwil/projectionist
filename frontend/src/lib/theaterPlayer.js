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
