/** Pure helpers for Projectionist `/live` watch + guide. */

import { ROUTES } from "./backNav.js";
import {
  formatProgramDisplayTitle,
  formatProgramEpisodeLabel,
} from "./liveProgramDetail.js";

/** Living-room empty copy for Live CC when neither stream nor Plex tracks exist. */
export const LIVE_CC_EMPTY_STREAM = "No subtitles on this stream";
export const LIVE_CC_EMPTY_AIRING = "No captions available for this airing";

/**
 * Merge HLS/native stream tracks with Plex-attached tracks for the CC picker.
 * Stream tracks win for in-player display; Plex rows fill when the encode is bare.
 */
export function mergeLiveCcTracks(streamTracks = [], plexPayload = null) {
  const stream = Array.isArray(streamTracks) ? streamTracks : [];
  const plexRows = Array.isArray(plexPayload?.plex_streams) ? plexPayload.plex_streams : [];
  const plex = plexRows.map((row, index) => ({
    index: `plex-${row.id || index}`,
    label: row.label || row.display_title || row.language || `Plex ${index + 1}`,
    language: row.language_code || row.language || "",
    viaPlex: true,
    proxyUrl: row.proxy_url || "",
    streamId: row.id || "",
  }));
  const hasAny = stream.length > 0 || plex.length > 0;
  let emptyMessage = "";
  if (!hasAny) {
    emptyMessage = plexPayload
      ? String(plexPayload.empty_message || LIVE_CC_EMPTY_AIRING)
      : LIVE_CC_EMPTY_STREAM;
  }
  return {
    streamTracks: stream,
    plexTracks: plex,
    canDownload: Boolean(plexPayload?.can_download),
    plexRatingKey: plexPayload?.plex_rating_key || "",
    emptyMessage,
    hasAny,
  };
}

export function liveStreamUrl(channelId) {
  const id = encodeURIComponent(String(channelId || "").trim());
  if (!id) return "";
  return `/api/live-channels/stream/${id}/index.m3u8`;
}

export function liveWatchHref(channelId, { popout = false } = {}) {
  const params = new URLSearchParams();
  const id = String(channelId || "").trim();
  if (id) params.set("channel", id);
  const path = popout ? ROUTES.liveWatch : ROUTES.live;
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Opener guide URL after pop-out — keeps channel selected without starting HLS. */
export function liveGuideHref(channelId) {
  const params = new URLSearchParams();
  const id = String(channelId || "").trim();
  if (id) params.set("channel", id);
  params.set("mode", "guide");
  return `${ROUTES.live}?${params.toString()}`;
}

/**
 * Single-session pop-out handoff: TV window URL + opener guide URL.
 * Caller must window.open(popoutHref) synchronously, then navigate opener to guideHref
 * so the original LivePlayer unloads before the pop-out tunes.
 */
export function popoutHandoff(channelId) {
  const id = String(channelId || "").trim();
  return {
    popoutHref: liveWatchHref(id, { popout: true }),
    guideHref: liveGuideHref(id),
  };
}

/** True when a click landed on OSD / chrome controls (not the video stage). */
export function isLivePlayerChromeTarget(target) {
  if (!target || typeof target.closest !== "function") return false;
  return Boolean(
    target.closest(
      "button, a, input, select, textarea, [role='button'], .live-osd-actions, .live-cc-picker, .live-program-hover, .live-chrome",
    ),
  );
}

/** Idle delay before the cable-box OSD slides away (Watch + pop-out). */
export const OSD_IDLE_MS = 3500;

/**
 * Whether a pointer/mouse move should reveal or keep the OSD visible.
 *
 * Browsers fire a zero-delta `mousemove` when an overlay disappears under a
 * stationary cursor. Treating those as activity creates a hide↔show loop that
 * leaves the detail pane stuck on screen — especially in the small `/live/watch`
 * pop-out where the cursor often rests over the OSD.
 *
 * @param {{x: number, y: number}|null|undefined} prev
 * @param {{clientX?: number, clientY?: number}|null|undefined} next
 * @returns {{bump: boolean, pos: {x: number, y: number}|null}}
 */
export function shouldBumpOsdFromPointerMove(prev, next) {
  const x = Number(next?.clientX);
  const y = Number(next?.clientY);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return { bump: true, pos: prev || null };
  }
  if (
    prev &&
    Number.isFinite(prev.x) &&
    Number.isFinite(prev.y) &&
    prev.x === x &&
    prev.y === y
  ) {
    return { bump: false, pos: prev };
  }
  return { bump: true, pos: { x, y } };
}

/**
 * Start playback with muted-first fallback (pop-out / Safari autoplay).
 * @param {HTMLMediaElement|null|undefined} video
 * @returns {Promise<"playing"|"ready"|"idle">}
 */
export async function tryPlayLiveVideo(video) {
  if (!video) return "idle";
  try {
    await video.play();
    return "playing";
  } catch {
    const preferUnmuted = !video.muted;
    try {
      video.muted = true;
      await video.play();
      if (preferUnmuted) {
        video.muted = false;
      }
      return "playing";
    } catch {
      return "ready";
    }
  }
}

/**
 * Toggle pause ↔ play for live HLS. Pause freezes; play resumes (caller may startLoad).
 * @param {HTMLMediaElement|null|undefined} video
 * @returns {Promise<"playing"|"paused"|"ready"|"idle">}
 */
export async function toggleLiveVideoPlayback(video) {
  if (!video) return "idle";
  if (!video.paused) {
    video.pause();
    return "paused";
  }
  return tryPlayLiveVideo(video);
}

/** Escalate brief buffering copy to “stalled — retrying” after this many ms. */
export const LIVE_STALL_ESCALATE_MS = 4000;

/** Max ring-buffer entries retained on ``window.__projectionistLiveDiag``. */
export const LIVE_DIAG_RING_MAX = 40;

/**
 * Snapshot media element state for stall diagnostics.
 * @param {HTMLMediaElement|null|undefined} video
 */
export function summarizeLiveVideoBuffer(video) {
  if (!video) return null;
  const ranges = [];
  try {
    const buffered = video.buffered;
    for (let i = 0; i < buffered.length; i += 1) {
      ranges.push({
        start: Number(buffered.start(i).toFixed(3)),
        end: Number(buffered.end(i).toFixed(3)),
      });
    }
  } catch {
    // InvalidStateError before metadata — ignore.
  }
  return {
    readyState: video.readyState,
    networkState: video.networkState,
    currentTime: Number(Number(video.currentTime || 0).toFixed(3)),
    paused: Boolean(video.paused),
    ended: Boolean(video.ended),
    muted: Boolean(video.muted),
    buffered: ranges,
  };
}

/**
 * True when an hls.js ERROR detail is a buffer underrun / stall nudge (often non-fatal).
 * @param {unknown} detail
 */
export function isHlsBufferStallDetail(detail) {
  const text = String(detail || "");
  return /bufferStalledError|bufferNudgeOnStall|BUFFER_STALLED|BUFFER_NUDGE_ON_STALL/i.test(
    text,
  );
}

/**
 * Classify mid-watch stream health for OSD honesty.
 *
 * Initial tune (`loading`), hard `error`, idle, and user `paused` stay `"ok"` so we
 * do not paint Buffering… over Tuning… / Pause / error chips.
 *
 * @param {{
 *   playbackStatus?: string,
 *   waiting?: boolean,
 *   mediaStalled?: boolean,
 *   hlsBufferStalled?: boolean,
 *   playheadFrozen?: boolean,
 *   waitingMs?: number,
 *   escalateMs?: number,
 * }} [input]
 * @returns {"ok"|"buffering"|"stalled"}
 */
export function classifyLiveStreamHealth({
  playbackStatus = "idle",
  waiting = false,
  mediaStalled = false,
  hlsBufferStalled = false,
  playheadFrozen = false,
  waitingMs = 0,
  escalateMs = LIVE_STALL_ESCALATE_MS,
} = {}) {
  if (
    playbackStatus === "loading"
    || playbackStatus === "error"
    || playbackStatus === "idle"
    || playbackStatus === "paused"
  ) {
    return "ok";
  }
  if (
    hlsBufferStalled
    || mediaStalled
    || playheadFrozen
    || (waiting && waitingMs >= escalateMs)
  ) {
    return "stalled";
  }
  if (waiting) return "buffering";
  return "ok";
}

/**
 * Append a structured live-playback diagnostic and mirror it to the console.
 * Owners can inspect ``window.__projectionistLiveDiag`` after a freeze.
 *
 * @param {string} event
 * @param {Record<string, unknown>} [payload]
 * @param {{ ringMax?: number, sink?: { info?: Function }|null }} [options]
 */
export function recordLivePlaybackDiag(event, payload = {}, options = {}) {
  const ringMax = Number(options.ringMax) > 0 ? Number(options.ringMax) : LIVE_DIAG_RING_MAX;
  const entry = {
    t: new Date().toISOString(),
    event: String(event || "event"),
    ...payload,
  };
  const sink = options.sink !== undefined ? options.sink : console;
  try {
    sink?.info?.("[live-playback]", entry.event, entry);
  } catch {
    // ignore logging failures
  }
  if (typeof globalThis !== "undefined") {
    const root = globalThis;
    if (!Array.isArray(root.__projectionistLiveDiag)) {
      root.__projectionistLiveDiag = [];
    }
    root.__projectionistLiveDiag.push(entry);
    while (root.__projectionistLiveDiag.length > ringMax) {
      root.__projectionistLiveDiag.shift();
    }
  }
  return entry;
}

export function formatClock(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "";
  const total = Math.max(0, Math.round(Number(seconds)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatWallTime(epochSeconds) {
  if (epochSeconds == null || !Number.isFinite(Number(epochSeconds))) return "";
  try {
    return new Date(Number(epochSeconds) * 1000).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * Effective airing window for a guide program.
 * Caps padded guide ``stop`` at file ``durationSeconds`` when present (past-EOF).
 * @param {object|null|undefined} program
 * @returns {{start: number|null, stop: number|null}}
 */
export function programAiringBounds(program) {
  if (!program || typeof program !== "object") return { start: null, stop: null };
  const startRaw = program.start ?? program.started_at;
  const stopRaw = program.stop ?? program.ends_at;
  const start = Number.isFinite(Number(startRaw)) ? Number(startRaw) : null;
  let stop = Number.isFinite(Number(stopRaw)) ? Number(stopRaw) : null;
  let durationSec = null;
  if (program.durationSeconds != null && Number.isFinite(Number(program.durationSeconds))) {
    durationSec = Number(program.durationSeconds);
  } else if (program.duration_seconds != null && Number.isFinite(Number(program.duration_seconds))) {
    durationSec = Number(program.duration_seconds);
  } else if (program.duration != null && Number.isFinite(Number(program.duration))) {
    const raw = Number(program.duration);
    durationSec = raw >= 1000 ? raw / 1000 : raw;
  }
  if (stop == null && start != null && durationSec != null) {
    stop = start + durationSec;
  }
  if (start != null && durationSec != null) {
    const fileEnd = start + durationSec;
    stop = stop == null ? fileEnd : Math.min(stop, fileEnd);
  }
  return { start, stop };
}

function programsMatch(a, b) {
  if (!a || !b) return false;
  const aStart = Number(a.start ?? a.started_at);
  const bStart = Number(b.start ?? b.started_at);
  const aTitle = String(a.title || "").trim();
  const bTitle = String(b.title || "").trim();
  if (!aTitle || !bTitle || !Number.isFinite(aStart) || !Number.isFinite(bStart)) return false;
  return aTitle === bTitle && aStart === bStart;
}

function toOsdProgram(program) {
  if (!program || typeof program !== "object") return null;
  const title = String(program.title || "").trim();
  if (!title) return null;
  const { start, stop } = programAiringBounds(program);
  const episodeTitle = String(program.episode_title || "").trim();
  return {
    ...program,
    title,
    episode_title: episodeTitle || null,
    episode: program.episode ?? program.episode_number ?? null,
    content_rating: String(program.content_rating || program.rating || "").trim() || null,
    start,
    stop,
    started_at: start,
    ends_at: stop,
    is_flex: Boolean(program.isFlex ?? program.is_flex),
    is_paused: Boolean(program.is_paused ?? program.isPaused),
    plex_rating_key: program.plex_rating_key || program.plexRatingKey || null,
    show_plex_rating_key: program.show_plex_rating_key || program.showPlexRatingKey || null,
  };
}

/**
 * Pick airing + following program (mirrors backend pick_now_and_next).
 * Latest start wins among overlaps; past-EOF padded stops do not stay airing.
 *
 * @param {object[]} programs
 * @param {number} nowSec
 * @param {{ selectedProgram?: object|null }} [options]
 */
export function pickNowAndNext(programs, nowSec, { selectedProgram = null } = {}) {
  const ts = Number(nowSec);
  const ordered = (Array.isArray(programs) ? programs : [])
    .filter((p) => p && typeof p === "object" && String(p.title || "").trim())
    .slice()
    .sort((a, b) => {
      const as = Number(a.start ?? a.started_at);
      const bs = Number(b.start ?? b.started_at);
      return (Number.isFinite(as) ? as : 0) - (Number.isFinite(bs) ? bs : 0);
    });

  const airing = [];
  let firstFuture = null;
  for (let index = 0; index < ordered.length; index += 1) {
    const program = ordered[index];
    const { start, stop } = programAiringBounds(program);
    if (start != null && stop != null && start <= ts && ts < stop) {
      airing.push({ start, index, program });
      continue;
    }
    if (firstFuture == null && start != null && start > ts && !airing.length) {
      firstFuture = program;
    }
  }

  let nowProg = null;
  let nextProg = null;
  if (airing.length) {
    airing.sort((a, b) => a.start - b.start);
    const chosen = airing[airing.length - 1];
    nowProg = toOsdProgram(chosen.program);
    for (let j = chosen.index + 1; j < ordered.length; j += 1) {
      nextProg = toOsdProgram(ordered[j]);
      if (nextProg) break;
    }
  } else if (firstFuture) {
    nextProg = toOsdProgram(firstFuture);
  }

  const selected = selectedProgram && typeof selectedProgram === "object" ? selectedProgram : null;
  if (selected) {
    const { start: selStart, stop: selStop } = programAiringBounds(selected);
    const selectedAiring =
      selStart != null && selStop != null && selStart <= ts && ts < selStop;
    const selectedIsNext = nextProg && programsMatch(selected, nextProg);
    // Explicit guide click: prefer the selected airing, or promote the clicked
    // next title once the prior slot is dead (past EOF / past stop).
    if (
      selectedAiring
      || (!nowProg && selectedIsNext)
      || (!nowProg && selStart != null && selStart <= ts)
    ) {
      nowProg = toOsdProgram(selected);
      nextProg = null;
      const selIdx = ordered.findIndex((p) => programsMatch(p, selected));
      if (selIdx >= 0) {
        for (let j = selIdx + 1; j < ordered.length; j += 1) {
          nextProg = toOsdProgram(ordered[j]);
          if (nextProg) break;
        }
      }
    } else if (
      !nowProg
      && selStart != null
      && selStart > ts
      && programsMatch(selected, firstFuture)
    ) {
      // Clicked the upcoming title while nothing is airing — show it as now.
      nowProg = toOsdProgram(selected);
      nextProg = null;
      const selIdx = ordered.findIndex((p) => programsMatch(p, selected));
      if (selIdx >= 0) {
        for (let j = selIdx + 1; j < ordered.length; j += 1) {
          nextProg = toOsdProgram(ordered[j]);
          if (nextProg) break;
        }
      }
    }
  }

  if (!nowProg && !nextProg && ordered.length) {
    nowProg = toOsdProgram(ordered[0]);
    if (ordered.length > 1) nextProg = toOsdProgram(ordered[1]);
  }

  return { now: nowProg, next: nextProg };
}

/**
 * Stable guide-cell key for selection highlighting / tune handoff.
 * @param {string} channelId
 * @param {object|null|undefined} program
 */
export function liveProgramKey(channelId, program) {
  if (!program) return "";
  const start = program.start ?? program.started_at;
  const title = String(program.title || "").trim();
  if (start == null || !title) return "";
  return `${String(channelId || "")}:${start}:${title}`;
}

/**
 * @param {object|null|undefined} channel
 * @param {number} [nowMs]
 * @param {{ selectedProgram?: object|null }} [options]
 */
export function buildOsdModel(channel, nowMs = Date.now(), { selectedProgram = null } = {}) {
  if (!channel || typeof channel !== "object") return null;
  const nowSec = nowMs / 1000;
  const programs = Array.isArray(channel.programs) ? channel.programs : [];
  let now = null;
  let next = null;
  if (programs.length) {
    const slots = pickNowAndNext(programs, nowSec, { selectedProgram });
    now = slots.now;
    next = slots.next;
  } else {
    now = channel.now && typeof channel.now === "object" ? toOsdProgram(channel.now) : null;
    next = channel.next && typeof channel.next === "object" ? toOsdProgram(channel.next) : null;
    // Stale snapshot fallback: drop a dead "now" once remaining hits 0.
    if (now) {
      const { start: deadStart, stop: deadStop } = programAiringBounds(now);
      if (deadStart != null && deadStop != null && nowSec >= deadStop) {
        if (next && Number(next.start ?? next.started_at) <= nowSec) {
          now = next;
          next = null;
        } else {
          now = null;
        }
      }
    }
  }

  let secondsElapsed = now?.seconds_elapsed ?? null;
  let secondsRemaining = now?.seconds_remaining ?? null;
  let percent = now?.percent ?? null;
  const start = now?.started_at ?? now?.start ?? null;
  const end = now?.ends_at ?? now?.stop ?? null;
  if (start != null && end != null && Number.isFinite(Number(start)) && Number.isFinite(Number(end))) {
    const duration = Math.max(0, Number(end) - Number(start));
    if (duration > 0) {
      if (nowSec < Number(start)) {
        secondsElapsed = 0;
        secondsRemaining = duration;
        percent = 0;
      } else {
        secondsElapsed = Math.max(0, Math.min(duration, nowSec - Number(start)));
        secondsRemaining = Math.max(0, Number(end) - nowSec);
        percent = Math.max(0, Math.min(100, (secondsElapsed / duration) * 100));
      }
    }
  }
  const durationSeconds =
    start != null && end != null ? Math.max(0, Number(end) - Number(start)) : null;
  const isFlex = Boolean(now?.is_flex);
  const nextTitle = String(next?.title || "").trim();
  const nextEpisode = formatProgramEpisodeLabel(next) || String(next?.episode_title || "").trim();
  const nextDisplay = formatProgramDisplayTitle(next) || nextTitle;
  // During Continuity/flex, never show a stolen content episode on "now" — the
  // upcoming show belongs in Next (and optionally as an Up-next subtitle).
  let title = String(now?.title || "").trim();
  let episode = isFlex ? "" : formatProgramEpisodeLabel(now) || String(now?.episode_title || "").trim();
  if (isFlex && nextDisplay) {
    episode = `Up next: ${nextDisplay}`;
  } else if (isFlex && nextTitle && !title.toLowerCase().includes("up next")) {
    episode = `Up next: ${nextTitle}`;
  }
  return {
    id: String(channel.id || ""),
    number: channel.number == null ? null : Number(channel.number),
    name: String(channel.name || "Channel").trim() || "Channel",
    iconUrl: String(channel.icon_url || channel.iconUrl || "").trim(),
    title,
    episode,
    rating: isFlex ? "" : String(now?.content_rating || "").trim(),
    isFlex,
    nowProgram: isFlex ? null : now,
    nextProgram: next,
    nextTitle,
    nextEpisode,
    nextDisplay,
    nextStart: next?.started_at ?? next?.start ?? null,
    secondsElapsed,
    secondsRemaining,
    durationSeconds,
    percent,
    isPaused: Boolean(now?.is_paused),
    plexRatingKey: String(now?.plex_rating_key || "").trim(),
    showPlexRatingKey: String(now?.show_plex_rating_key || "").trim(),
  };
}

/**
 * Map a guide/on-now program into the EPG cell shape (episode title + dig-in fields).
 * @param {object} program
 */
function normalizeGuideProgram(program) {
  const title = String(program.title || "").trim();
  if (!title) return null;
  const episode =
    formatProgramEpisodeLabel(program) || String(program.episode_title || "").trim();
  // Prefer guide start/stop for EPG width; ends_at may be file-EOF capped.
  const start = program.start ?? program.started_at ?? null;
  const stop = program.stop ?? program.ends_at ?? null;
  let durationSeconds = null;
  if (program.duration_seconds != null && Number.isFinite(Number(program.duration_seconds))) {
    durationSeconds = Number(program.duration_seconds);
  } else if (program.durationSeconds != null && Number.isFinite(Number(program.durationSeconds))) {
    durationSeconds = Number(program.durationSeconds);
  }
  return {
    title,
    episode,
    episode_title: String(program.episode_title || "").trim(),
    season: program.season ?? null,
    episode_number: program.episode ?? program.episode_number ?? null,
    year: program.year ?? null,
    overview: String(program.overview || "").trim(),
    media_type: String(program.media_type || "").trim(),
    rating: String(program.content_rating || "").trim(),
    content_rating: String(program.content_rating || "").trim(),
    start,
    stop,
    durationSeconds,
    duration_seconds: durationSeconds,
    isFlex: Boolean(program.is_flex),
    is_flex: Boolean(program.is_flex),
    plex_rating_key: program.plex_rating_key || null,
    show_plex_rating_key: program.show_plex_rating_key || null,
  };
}

/**
 * Normalize guide API into EPG rows with programs.
 * @param {object|null|undefined} snapshot
 */
export function normalizeGuide(snapshot) {
  if (!snapshot || typeof snapshot !== "object" || !snapshot.enabled) return null;
  const generatedAt = Number(snapshot.generated_at) || Date.now() / 1000;
  const windowSeconds = Number(snapshot.window_seconds) || 6 * 3600;
  const channels = (Array.isArray(snapshot.channels) ? snapshot.channels : [])
    .map((channel) => {
      if (!channel || typeof channel !== "object") return null;
      const programs = (Array.isArray(channel.programs) ? channel.programs : [])
        .map((program) =>
          program && typeof program === "object" ? normalizeGuideProgram(program) : null,
        )
        .filter(Boolean);
      // Ensure now/next appear even when programs list is thin.
      if (!programs.length && channel.now) {
        const fallback = normalizeGuideProgram(channel.now);
        if (fallback) programs.push(fallback);
      }
      return {
        id: String(channel.id || ""),
        name: String(channel.name || "Channel").trim() || "Channel",
        number: channel.number == null ? null : Number(channel.number),
        iconUrl: String(channel.icon_url || "").trim(),
        now: channel.now || null,
        next: channel.next || null,
        programs,
      };
    })
    .filter(Boolean);

  return {
    enabled: true,
    ready: Boolean(snapshot.ready) && channels.length > 0,
    reason: String(snapshot.reason || ""),
    generatedAt,
    windowStart: generatedAt,
    windowEnd: generatedAt + windowSeconds,
    hours: Number(snapshot.hours) || windowSeconds / 3600,
    watchHint: String(snapshot.watch_hint || snapshot.plex_hint || ""),
    channels,
  };
}

/** Pixel layout for a program cell in a horizontal EPG. */
export function programCellStyle(program, windowStart, windowEnd, pxPerHour) {
  const start = Number(program?.start);
  const stop = Number(program?.stop);
  if (!Number.isFinite(start) || !Number.isFinite(stop) || stop <= start) {
    return { display: "none" };
  }
  const clampedStart = Math.max(start, windowStart);
  const clampedStop = Math.min(stop, windowEnd);
  if (clampedStop <= clampedStart) return { display: "none" };
  const leftHours = (clampedStart - windowStart) / 3600;
  const widthHours = (clampedStop - clampedStart) / 3600;
  return {
    left: `${leftHours * pxPerHour}px`,
    width: `${Math.max(48, widthHours * pxPerHour)}px`,
  };
}

export function adjacentChannelId(channels, currentId, delta) {
  const list = Array.isArray(channels) ? channels : [];
  if (!list.length) return "";
  const idx = list.findIndex((c) => c.id === currentId);
  if (idx < 0) return list[0]?.id || "";
  const next = Math.max(0, Math.min(list.length - 1, idx + delta));
  return list[next]?.id || "";
}
