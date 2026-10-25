/** Pure helpers for Projectionist's one subtitle model (Live + Play). */

export const SUBTITLE_FETCH_FAILED =
  "Couldn’t load this subtitle track from Plex. Try another track, or watch in Plex.";
export const SUBTITLE_EMPTY_TRACKS = "No subtitle tracks are attached to this title in Plex.";
export const SUBTITLE_NO_TEXT_TRACKS = "No text captions we can draw. Off stays Off.";
export const SUBTITLE_DELAY_STEP_SEC = 0.5;
export const SUBTITLE_DELAY_MAX_SEC = 30;
export const SUBTITLE_BURN_IN_NOTE = "Plex captions restart playback. Timing is overlay-only.";
export const IMAGE_SUBTITLE_FORMATS = new Set([
  "pgs",
  "hdmv_pgs_subtitle",
  "hdmv_text_subtitle",
  "vobsub",
  "dvd_subtitle",
  "dvdsub",
  "dvb_subtitle",
  "dvbsub",
  "xsub",
]);
const BURN_IN_LANGUAGE_NAMES = {
  en: "English",
  eng: "English",
  es: "Spanish",
  spa: "Spanish",
  fr: "French",
  fra: "French",
  fre: "French",
  de: "German",
  ger: "German",
  deu: "German",
  ja: "Japanese",
  jpn: "Japanese",
  ko: "Korean",
  kor: "Korean",
  zh: "Chinese",
  chi: "Chinese",
  zho: "Chinese",
  pt: "Portuguese",
  por: "Portuguese",
  it: "Italian",
  ita: "Italian",
  ru: "Russian",
  rus: "Russian",
  ar: "Arabic",
  ara: "Arabic",
};

/** "00:01:02.500" | "01:02.500" | "1:02,5" → seconds (NaN when unparseable). */
export function parseCueTimestamp(raw) {
  const text = String(raw || "").trim().replace(",", ".");
  const parts = text.split(":");
  if (parts.length < 2 || parts.length > 3) return Number.NaN;
  const nums = parts.map((part) => Number(part));
  if (nums.some((n) => !Number.isFinite(n))) return Number.NaN;
  const [h, m, s] = parts.length === 3 ? nums : [0, nums[0], nums[1]];
  return h * 3600 + m * 60 + s;
}

/** Strip WebVTT/SRT/ASS markup to safe plain text (rendered with pre-line, never as HTML). */
export function cleanCueText(raw) {
  return String(raw || "")
    .replace(/\{\\[^}]*\}/g, "")
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\\N/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
}

/**
 * Parse WebVTT (the proxy always returns WebVTT) into sorted cues.
 * @returns {{ start: number, end: number, text: string }[]}
 */
export function parseVtt(source) {
  const lines = String(source || "").replace(/\r\n?/g, "\n").replace(/^\ufeff/, "").split("\n");
  const cues = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.includes("-->")) {
      i += 1;
      continue;
    }
    const [startRaw, endRaw] = line.split("-->");
    const start = parseCueTimestamp(startRaw);
    const end = parseCueTimestamp(String(endRaw || "").trim().split(/\s+/)[0]);
    i += 1;
    const body = [];
    while (i < lines.length && lines[i].trim() !== "") {
      body.push(lines[i]);
      i += 1;
    }
    const text = cleanCueText(body.join("\n"));
    if (Number.isFinite(start) && Number.isFinite(end) && end > start && text) {
      cues.push({ start, end, text });
    }
  }
  cues.sort((a, b) => a.start - b.start);
  return cues;
}

/**
 * Media seconds used to look up soft-subtitle cues.
 * Adds seek-origin (0-based Plex restart timeline) then applies sync delay:
 * positive delaySec = show cues later; negative = earlier.
 */
export function subtitleLookupTimeSec({ currentTimeSec, originMs = 0, delaySec = 0 } = {}) {
  const media = Number(currentTimeSec);
  if (!Number.isFinite(media)) return Number.NaN;
  const originSec = Math.max(0, (Number(originMs) || 0) / 1000);
  const delay = Number(delaySec);
  const shift = Number.isFinite(delay) ? delay : 0;
  return Math.max(0, media) + originSec - shift;
}

/**
 * One presentation path only: Plex burn-in, soft DOM overlay, native TextTrack, or none.
 * Never overlay + burn-in. Soft tracks win over native — never stack systems.
 */
export function resolveSubtitlePresentation({
  softTrackSelected = false,
  softTrackReady = false,
  nativeTrackIndex = -1,
  burnInSelected = false,
} = {}) {
  // Burn-in is in the picture. Never overlay on top of it.
  if (burnInSelected) {
    return {
      mode: "burn",
      showOverlay: false,
      enableNativeTrack: false,
      disableAllNative: true,
    };
  }
  if (softTrackSelected) {
    return {
      mode: softTrackReady ? "soft" : "soft-loading",
      showOverlay: Boolean(softTrackReady),
      enableNativeTrack: false,
      disableAllNative: true,
    };
  }
  if (typeof nativeTrackIndex === "number" && nativeTrackIndex >= 0) {
    return {
      mode: "native",
      showOverlay: false,
      enableNativeTrack: true,
      disableAllNative: false,
      nativeTrackIndex,
    };
  }
  return {
    mode: "off",
    showOverlay: false,
    enableNativeTrack: false,
    disableAllNative: true,
  };
}

/** Disable every TextTrack on a media element (burn-in / HLS WebVTT must not stack). */
export function silenceNativeTextTracks(video) {
  const list = video?.textTracks;
  if (!list || typeof list.length !== "number") return 0;
  let n = 0;
  for (let i = 0; i < list.length; i += 1) {
    const track = list[i];
    if (!track) continue;
    if (track.mode !== "disabled") {
      track.mode = "disabled";
      n += 1;
    }
  }
  return n;
}

/**
 * Text of the active cue at ``timeSec``.
 * Overlapping cues: keep the latest-started line so SDH stacks do not paint
 * unreadably on top of each other (multi-system doubling is handled elsewhere).
 */
export function activeCueText(cues, timeSec) {
  if (!Array.isArray(cues) || !cues.length || !Number.isFinite(timeSec)) return "";
  let best = null;
  for (const cue of cues) {
    if (cue.start > timeSec) break;
    if (timeSec < cue.end) best = cue;
  }
  return best?.text || "";
}

export function clampSubtitleDelay(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(-SUBTITLE_DELAY_MAX_SEC, Math.min(SUBTITLE_DELAY_MAX_SEC, Math.round(n * 10) / 10));
}

export function formatSubtitleDelay(value) {
  const n = clampSubtitleDelay(value);
  if (n === 0) return "In sync";
  return `${n > 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}s`;
}

export function stepSubtitleDelay(current, delta = SUBTITLE_DELAY_STEP_SEC) {
  return clampSubtitleDelay((Number(current) || 0) + (Number(delta) || 0));
}

/** en ↔ eng, en-US → en. Empty values never match. */
export function subtitleLanguageMatches(language, code) {
  const wanted = String(code || "")
    .trim()
    .toLowerCase()
    .split("-")[0];
  const have = String(language || "")
    .trim()
    .toLowerCase()
    .split("-")[0];
  if (!wanted || !have) return false;
  if (have === wanted) return true;
  if (have.length === 3 && wanted.length === 2 && have.startsWith(wanted)) return true;
  if (wanted.length === 3 && have.length === 2 && wanted.startsWith(have)) return true;
  return false;
}

/**
 * Normalize server rows (`plex_streams` on Live, `streams` on library items) into picker tracks.
 * Image-based / unreadable tracks are omitted — dead “can’t draw” chips are not a choice.
 */
export function normalizeSubtitleTracks(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return list
    .filter((row) => row && typeof row === "object")
    .map((row, index) => {
      const id = String(row.id ?? index);
      const proxyUrl = String(row.proxy_url || "");
      const renderable = row.renderable !== false && Boolean(proxyUrl);
      return {
        index: `plex-${id}`,
        id,
        label: String(row.label || row.display_title || row.language || `Track ${index + 1}`),
        language: String(row.language_code || row.language || ""),
        proxyUrl,
        renderable,
        unavailableReason: renderable ? "" : String(row.unavailable_reason || ""),
        selected: Boolean(row.selected),
        forced: Boolean(row.forced),
      };
    })
    .filter((track) => track.renderable);
}

export function isImageSubtitleStream(row) {
  if (!row || typeof row !== "object") return false;
  if (row.image === true) return true;
  const fmt = String(row.format || "").trim().toLowerCase();
  return IMAGE_SUBTITLE_FORMATS.has(fmt);
}

export function plexBurnInLanguageLabel(row) {
  const language = String(row?.language || "").trim();
  if (language && !/^[a-z]{2,3}$/i.test(language)) return language;
  const code = String(row?.language_code || language || "")
    .trim()
    .toLowerCase()
    .split("-")[0];
  return BURN_IN_LANGUAGE_NAMES[code] || language || (code ? code.toUpperCase() : "Captions");
}

/** Last-resort chip: language name plus “from Plex”. Never “can’t draw”. */
export function plexBurnInChipLabel(row) {
  return `${plexBurnInLanguageLabel(row)} (from Plex)`;
}

/**
 * Bitmap streams for languages that still have no drawable overlay text.
 * One chip per language; never auto-selected. Member must pick burn-in.
 */
export function plexBurnInFallbackTracks(streams, overlayTracks = []) {
  const overlayLangs = (overlayTracks || []).filter((track) => track?.renderable !== false);
  const byLang = new Map();
  const list = Array.isArray(streams) ? streams : [];
  for (const row of list) {
    if (!isImageSubtitleStream(row)) continue;
    const language = String(row.language_code || row.language || "");
    if (language && preferredPickableSubtitle(overlayLangs, [language])) continue;
    const id = String(row.id ?? "");
    if (!id) continue;
    const langKey = String(language || id)
      .trim()
      .toLowerCase()
      .split("-")[0] || id;
    const next = {
      index: `plex-burn-${id}`,
      id,
      label: plexBurnInChipLabel(row),
      language,
      proxyUrl: "",
      renderable: false,
      burnIn: true,
      forced: Boolean(row.forced),
    };
    const existing = byLang.get(langKey);
    if (!existing || (existing.forced && !next.forced)) {
      byLang.set(langKey, next);
    }
  }
  return [...byLang.values()];
}

export function preferredPickableSubtitle(tracks, preferredLanguages = ["en"]) {
  const pickable = (tracks || []).filter((track) => track.renderable);
  const langs = (preferredLanguages || []).map((code) => String(code || "").trim()).filter(Boolean);
  const wanted = langs.length ? langs : ["en"];
  for (const code of wanted) {
    const hit = pickable.find((track) => subtitleLanguageMatches(track.language, code) && !track.forced);
    if (hit) return hit;
  }
  for (const code of wanted) {
    const hit = pickable.find((track) => subtitleLanguageMatches(track.language, code));
    if (hit) return hit;
  }
  return null;
}

/** True when the preferred language has no text track we can overlay. */
export function needsTextSubtitleFetch(tracks, preferredLanguages = ["en"]) {
  return !preferredPickableSubtitle(tracks, preferredLanguages);
}

/**
 * Play CC list: hide undrawable rows; after a Plex text-track download, auto-select
 * the preferred language when that fetch was required.
 */
export function resolvePlaySubtitleTracks({
  listedStreams = [],
  downloadedStreams = null,
  preferredLanguages = ["en"],
} = {}) {
  const listed = normalizeSubtitleTracks(listedStreams);
  const needsFetch = needsTextSubtitleFetch(listed, preferredLanguages);
  const source =
    needsFetch && Array.isArray(downloadedStreams)
      ? normalizeSubtitleTracks(downloadedStreams)
      : listed;
  const tracks = source.filter((track) => track.renderable);
  const auto = needsFetch ? preferredPickableSubtitle(tracks, preferredLanguages) : null;
  const burnInTracks = plexBurnInFallbackTracks(
    [...(Array.isArray(listedStreams) ? listedStreams : []), ...(Array.isArray(downloadedStreams) ? downloadedStreams : [])],
    tracks,
  );
  return {
    tracks,
    burnInTracks,
    needsFetch,
    autoSelectIndex: auto?.index ?? -1,
    empty: tracks.length === 0,
  };
}

/**
 * Seconds into a Live airing: wall clock minus the program's scheduled start.
 * Live encodes are cut at the schedule offset, so this tracks the movie timeline.
 */
export function liveProgramClockSec(osd, nowMs = Date.now()) {
  const program = osd?.nowProgram;
  const start = Number(program?.started_at ?? program?.start);
  if (!Number.isFinite(start)) return null;
  return Math.max(0, nowMs / 1000 - start);
}
