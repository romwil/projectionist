/** Normalize owner Live Channels now-playing status into an ops table model. */

import { formatRemaining } from "./onNow.js";
import { formatWallTime } from "./liveChannels.js";

/** @typedef {"unreachable"|"empty"|"paused"|"streaming"|"airing"|"idle"|""} HealthChip */

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
      return "Streaming";
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
 *     nextTitle: string,
 *     nextWall: string,
 *     percent: number|null,
 *     secondsRemaining: number|null,
 *     progressHint: string,
 *     isPaused: boolean,
 *     health: string,
 *     healthLabel: string,
 *     warning: string,
 *     streamConnections: number,
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
      const nowTitle = String(row.now_title || row.title || "").trim();
      const nextTitle = String(row.next_title || "").trim();
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
      const health = String(row.health || "").trim();
      const progressParts = [];
      if (isPaused) {
        progressParts.push("Paused");
      } else {
        if (percent != null) progressParts.push(`${Math.round(percent)}%`);
        const remaining = formatRemaining(secondsRemaining);
        if (remaining) progressParts.push(remaining);
      }
      return {
        id: String(row.id || `${number ?? "x"}-${name}`),
        name,
        number,
        nowTitle,
        nextTitle,
        nextWall: formatWallTime(nextStart),
        percent,
        secondsRemaining,
        progressHint: progressParts.join(" · "),
        isPaused,
        health,
        healthLabel: formatHealthChip(health),
        warning: String(row.warning || "").trim(),
        streamConnections: Number(row.stream_connections) || 0,
        airingWhy: String(row.airing_why || "").trim(),
      };
    })
    .filter(Boolean);

  return { enabled, engineUp, rows };
}
