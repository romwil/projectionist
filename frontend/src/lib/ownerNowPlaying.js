/** Normalize owner Live Channels now-playing status into an ops table model. */

import { formatRemaining } from "./onNow.js";
import { formatWallTime } from "./liveChannels.js";

/** @typedef {"unreachable"|"empty"|"paused"|"streaming"|"airing"|"idle"|""} HealthChip */

/**
 * Tunarr fills empty lineups with a 6-hour "{Station} · Up next" placeholder.
 * @param {string|null|undefined} title
 * @returns {boolean}
 */
export function isPlaceholderNowTitle(title) {
  const text = String(title || "").trim();
  if (!text) return false;
  if (text.includes("· Up next")) return true;
  return /^(flex|filler|continuity)$/i.test(text);
}

/**
 * @param {string|null|undefined} health
 * @returns {string}
 */
export function formatHealthChip(health) {
  switch (String(health || "").trim()) {
    case "unreachable":
      return "TV unreachable";
    case "empty":
      return "Empty lineup";
    case "paused":
      return "Paused";
    case "streaming":
      // Stream count is metadata — never label a keepalive as "Streaming".
      return "Airing";
    case "airing":
      return "Airing";
    case "idle":
      return "Idle";
    default:
      return "";
  }
}

/**
 * @param {object|null|undefined} status
 * @returns {{
 *   enabled: boolean,
 *   engineUp: boolean,
 *   rows: Array<{
 *     id: string,
 *     name: string,
 *     number: number|null,
 *     nowTitle: string,
 *     nowKind: string,
 *     nextTitle: string,
 *     nextWall: string,
 *     percent: number|null,
 *     secondsRemaining: number|null,
 *     progressHint: string,
 *     showProgress: boolean,
 *     isPaused: boolean,
 *     isEmpty: boolean,
 *     slotEnded: boolean,
 *     health: string,
 *     healthLabel: string,
 *     warning: string,
 *     streamConnections: number,
 *     keepalive: boolean,
 *     lineupPrograms: number|null,
 *     airingWhy: string,
 *   }>,
 * }}
 */
export function normalizeOwnerNowPlaying(status) {
  if (!status || typeof status !== "object") {
    return { enabled: false, engineUp: false, rows: [] };
  }
  const enabled = Boolean(status.live_channels_enabled);
  const engineUp = Boolean(status.broadcast?.sidecar_up);
  const raw = Array.isArray(status.now_playing)
    ? status.now_playing
    : Array.isArray(status.airing)
      ? status.airing
      : [];

  const rows = raw
    .map((row) => {
      if (!row || typeof row !== "object") return null;
      const number =
        row.number == null || row.number === ""
          ? null
          : Number.isFinite(Number(row.number))
            ? Number(row.number)
            : null;
      const name = String(row.name || "Channel").trim() || "Channel";
      const rawNowTitle = String(row.now_title || row.title || "").trim();
      const nowKind = String(row.now_kind || "").trim()
        || (isPlaceholderNowTitle(rawNowTitle) ? "placeholder" : rawNowTitle ? "program" : "");
      const rawNextTitle = String(row.next_title || "").trim();
      const nextKind = String(row.next_kind || "").trim()
        || (isPlaceholderNowTitle(rawNextTitle) ? "placeholder" : "");
      const nextStart =
        row.next_start == null || !Number.isFinite(Number(row.next_start))
          ? null
          : Number(row.next_start);
      const percent =
        row.percent == null || !Number.isFinite(Number(row.percent))
          ? null
          : Math.max(0, Math.min(100, Number(row.percent)));
      const secondsRemaining =
        row.seconds_remaining == null || !Number.isFinite(Number(row.seconds_remaining))
          ? null
          : Math.max(0, Math.round(Number(row.seconds_remaining)));
      const isPaused = Boolean(row.is_paused);
      const lineupPrograms =
        row.lineup_programs == null || !Number.isFinite(Number(row.lineup_programs))
          ? null
          : Number(row.lineup_programs);
      let health = String(row.health || "").trim();
      if (health === "streaming") {
        health = lineupPrograms != null && lineupPrograms <= 0 ? "empty" : "airing";
      }
      const isEmpty =
        health === "empty"
        || (lineupPrograms != null && lineupPrograms <= 0)
        || (nowKind === "placeholder" && lineupPrograms == null);
      const placeholderNow = nowKind === "placeholder";
      const slotEnded =
        !isEmpty
        && nowKind === "program"
        && !isPaused
        && (percent === 100 || secondsRemaining === 0);
      const streamConnections = Number(row.stream_connections) || 0;
      const honestNext =
        rawNextTitle && nextKind !== "placeholder" ? rawNextTitle : "";

      let nowTitle = rawNowTitle;
      let nextTitle = honestNext;
      let progressHint = "";
      let showProgress = false;

      if (isEmpty) {
        nowTitle = "No lineup";
        nextTitle = "No upcoming";
        progressHint = "";
        showProgress = false;
      } else if (placeholderNow) {
        nowTitle = "Between programs";
        nextTitle = honestNext || "No upcoming";
        progressHint = "";
        showProgress = false;
      } else if (slotEnded) {
        nowTitle = rawNowTitle;
        nextTitle = honestNext;
        progressHint = "Slot ended";
        showProgress = false;
      } else if (isPaused) {
        nowTitle = rawNowTitle;
        nextTitle = honestNext;
        progressHint = "Paused";
        showProgress = percent != null;
      } else {
        nowTitle = rawNowTitle;
        nextTitle = honestNext;
        const progressParts = [];
        if (percent != null) progressParts.push(`${Math.round(percent)}%`);
        const remaining = formatRemaining(secondsRemaining);
        if (remaining) progressParts.push(remaining);
        progressHint = progressParts.join(" · ");
        showProgress = percent != null;
      }

      return {
        id: String(row.id || `${number ?? "x"}-${name}`),
        name,
        number,
        nowTitle,
        nowKind,
        nextTitle: isEmpty ? "No upcoming" : nextTitle,
        nextWall: isEmpty ? "" : formatWallTime(nextStart),
        percent: showProgress ? percent : null,
        secondsRemaining,
        progressHint,
        showProgress,
        isPaused,
        isEmpty,
        slotEnded,
        health: isEmpty ? "empty" : health,
        healthLabel: formatHealthChip(isEmpty ? "empty" : health),
        warning: String(row.warning || "").trim(),
        streamConnections,
        keepalive: streamConnections > 0,
        lineupPrograms,
        airingWhy: String(row.airing_why || "").trim(),
      };
    })
    .filter(Boolean);

  return { enabled, engineUp, rows };
}
