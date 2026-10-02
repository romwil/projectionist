/** Pure helpers for Projectionist's one subtitle model (Live + Play). */

export const SUBTITLE_FETCH_FAILED =
  "Couldn’t load this subtitle track from Plex. Try another track, or watch in Plex.";
export const SUBTITLE_EMPTY_TRACKS = "No subtitle tracks are attached to this title in Plex.";
export const SUBTITLE_DELAY_STEP_SEC = 0.5;
export const SUBTITLE_DELAY_MAX_SEC = 30;

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

/** Text of every cue showing at ``timeSec`` (overlapping cues stack). */
export function activeCueText(cues, timeSec) {
  if (!Array.isArray(cues) || !cues.length || !Number.isFinite(timeSec)) return "";
  const active = [];
  for (const cue of cues) {
    if (cue.start > timeSec) break;
    if (timeSec < cue.end) active.push(cue.text);
  }
  return active.join("\n");
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

/**
 * Normalize server rows (`plex_streams` on Live, `streams` on library items) into picker tracks.
 * Image-based tracks stay listed but flagged unavailable so we never pretend they render.
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
    });
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
