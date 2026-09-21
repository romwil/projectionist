/** Copy and chrome helpers for Admin → Libraries Sonarr Find all missing. */

const PHASE_LABELS = {
  idle: "Ready",
  queued: "Queued",
  scanning: "Scanning series",
  comparing: "Comparing to Wanted",
  done: "Scan finished",
  searching: "Queueing searches",
  searched: "Searches queued",
  error: "Failed",
};

export function sonarrMissingPhaseLabel(phase) {
  const key = String(phase || "").trim().toLowerCase();
  return PHASE_LABELS[key] || "Working";
}

export function sonarrWantedDeltaCopy(result) {
  if (!result) return "";
  const summary = String(result.summary || "").trim();
  if (summary) return summary;
  const scanCount = Number(result.scan_count) || 0;
  const wantedCount = Number(result.wanted_count) || 0;
  return `Library scan found ${scanCount}; Sonarr Wanted lists ${wantedCount}`;
}

export function sonarrMissingScanReady(status) {
  if (!status || status.busy) return false;
  const phase = String(status.phase || "");
  const result = status.result;
  if (!result) return false;
  const count =
    Number(result.scan_count) ||
    (Array.isArray(result.episode_ids) ? result.episode_ids.length : 0);
  if (count <= 0) return false;
  return phase === "done" || phase === "searched" || phase === "idle";
}

export function sonarrFindMissingButtonClass(status) {
  return sonarrMissingScanReady(status) ? "ghost" : "primary";
}

export function sonarrSearchMissingButtonClass(status) {
  return sonarrMissingScanReady(status) ? "primary" : "ghost";
}

export function sonarrMissingProgressLine(status) {
  if (!status) return "";
  const phase = String(status.phase || "idle");
  if (phase === "idle" && !status.result) return "";
  const bits = [];
  const message = String(status.message || "").trim();
  if (message) bits.push(message);
  const seriesTotal = Number(status.series_total) || 0;
  const seriesDone = Number(status.series_done) || 0;
  if (seriesTotal > 0) bits.push(`Series ${seriesDone} of ${seriesTotal}`);
  const missing = Number(status.missing_found) || 0;
  if (phase === "scanning" || phase === "comparing" || phase === "done" || missing) {
    bits.push(`${missing} missing`);
  }
  const queued = Number(status.searches_queued) || 0;
  if (phase === "searching" || phase === "searched" || queued) {
    bits.push(`${queued} searches queued`);
  }
  return bits.join(" · ");
}

export function sonarrMissingBySeries(result) {
  const groups = Array.isArray(result?.by_series) ? result.by_series : [];
  return groups
    .map((group) => ({
      seriesId: Number(group.seriesId) || 0,
      seriesTitle: String(group.seriesTitle || "Untitled"),
      count: Number(group.count) || (Array.isArray(group.episodes) ? group.episodes.length : 0),
      episodes: Array.isArray(group.episodes) ? group.episodes : [],
    }))
    .filter((group) => group.count > 0);
}
