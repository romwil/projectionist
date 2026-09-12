/** Unified Live Channels job rail + mutating-button helpers (approach B). */

export const LIVE_JOB_KIND_LABELS = {
  plex_refresh: "Refreshing Plex map",
  plex_rebuild: "Rebuilding tuner in Plex",
  engine: "Starting TV engine",
  continuity: "Rescanning filler",
  publish: "Publishing station",
  refill: "Refilling station",
};

export const LIVE_JOB_ALLOWED_BUSY = new Set(["status", "attach"]);

export function idleLiveJob() {
  return {
    kind: null,
    phase: "idle",
    percent: 0,
    message: "",
    startedAt: null,
    busy: false,
  };
}

export function isLiveJobBusy(job) {
  if (!job) return false;
  if (job.busy) return true;
  const phase = String(job.phase || "idle");
  return phase !== "idle" && phase !== "done" && phase !== "error" && phase !== "ready";
}

export function liveJobKindLabel(kind) {
  const key = String(kind || "").trim();
  return LIVE_JOB_KIND_LABELS[key] || "";
}

/**
 * Sticky rail copy: “Working: Refreshing Plex map · … · Don’t start another Live job.”
 */
export function liveJobRailCopy(job) {
  if (!isLiveJobBusy(job)) return "";
  const label = liveJobKindLabel(job.kind) || "Working";
  const bits = [`Working: ${label}`];
  const extra = String(job.message || "").trim();
  if (extra && extra !== label) bits.push(extra);
  const pct = Number(job.percent);
  if (Number.isFinite(pct) && pct > 0 && !extra.includes("%")) {
    bits.push(`${Math.min(100, Math.round(pct))}%`);
  }
  bits.push("Don’t start another Live job.");
  return bits.join(" · ");
}

export function liveJobSnippet(job) {
  if (!isLiveJobBusy(job)) return "";
  const label = liveJobKindLabel(job.kind) || "Working";
  const pct = Number(job.percent);
  const pctBit = Number.isFinite(pct) && pct > 0 ? ` · ${Math.min(100, Math.round(pct))}%` : "";
  return `${label}${pctBit}`;
}

/**
 * Disable mutating Live actions while a serialized job (or local mutating busy) is on.
 * Always allowed: Refresh status, copy URLs / Show Plex steps, tabs, form edits.
 */
export function isLiveMutatingDisabled(job, liveBusy) {
  if (isLiveJobBusy(job)) return true;
  const key = String(liveBusy || "").trim();
  if (!key) return false;
  if (LIVE_JOB_ALLOWED_BUSY.has(key)) return false;
  return true;
}

export function plexRebuildConfirmMessage() {
  return (
    "Rebuild tuner in Plex? This deletes and recreates the Tunarr device and XMLTV DVR "
    + "in Plex (OTA / antenna stays). Plex Media Server may hang briefly, and Tunarr Live "
    + "TV sessions drop. Over-the-air Live TV is not removed."
  );
}
