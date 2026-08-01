/** Multi-room couch handoff: absolute tune deep-links + sticky mini-OSD state. */

import { liveWatchHref } from "./liveChannels.js";

/**
 * @param {string} channelId
 * @param {{ origin?: string, popout?: boolean }} [options]
 * @returns {string}
 */
export function liveTuneAbsoluteUrl(channelId, { origin = "", popout = false } = {}) {
  const path = liveWatchHref(channelId, { popout });
  const base = String(origin || (typeof window !== "undefined" ? window.location.origin : "")).replace(
    /\/$/,
    "",
  );
  if (!base) return path;
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Build a CSP-safe SVG “link card” for couch handoff (not a standards QR).
 * Phones can still use copy-link; this card shows the deep-link for scan-adjacent use.
 * Returns "" when channel id is missing.
 *
 * @param {string} url
 * @returns {string}
 */
export function tuneLinkCardDataUrl(url) {
  const value = String(url || "").trim();
  if (!value) return "";
  const escaped = value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120">
  <rect width="320" height="120" fill="#111" rx="8"/>
  <text x="16" y="36" fill="#f4f1ea" font-family="ui-monospace,monospace" font-size="12">Tune link</text>
  <foreignObject x="16" y="48" width="288" height="56">
    <div xmlns="http://www.w3.org/1999/xhtml" style="color:#f4f1ea;font:11px/1.35 ui-monospace,monospace;word-break:break-all">${escaped}</div>
  </foreignObject>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

const STORAGE_KEY = "projectionist.liveStickyOsd";

/** @returns {{ channelId: string, channelName: string, nowTitle: string, updatedAt: number }|null} */
export function loadLiveStickyOsd() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.channelId) return null;
    return {
      channelId: String(parsed.channelId),
      channelName: String(parsed.channelName || "Live"),
      nowTitle: String(parsed.nowTitle || ""),
      updatedAt: Number(parsed.updatedAt) || Date.now(),
    };
  } catch {
    return null;
  }
}

/** @param {{ channelId?: string, channelName?: string, nowTitle?: string }|null} state */
export function saveLiveStickyOsd(state) {
  try {
    if (!state?.channelId) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        channelId: String(state.channelId),
        channelName: String(state.channelName || "Live"),
        nowTitle: String(state.nowTitle || ""),
        updatedAt: Date.now(),
      }),
    );
  } catch {
    // ignore
  }
}

export function clearLiveStickyOsd() {
  saveLiveStickyOsd(null);
}
