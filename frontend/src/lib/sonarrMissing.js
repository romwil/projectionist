/** Copy and chrome helpers for Admin → Libraries Sonarr Find all missing. */

const PHASE_LABELS = {
  idle: "Ready",
  queued: "Queued",
  scanning: "Scanning series",
  comparing: "Comparing to Wanted",
  done: "Scan finished",
  searching: "Submitting to Sonarr",
  executing: "Sonarr searching",
  searched: "Searches finished",
  cancelled: "Cancelled",
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
  return phase === "done" || phase === "searched" || phase === "idle" || phase === "cancelled";
}

export function sonarrFindMissingButtonClass(status) {
  return sonarrMissingScanReady(status) ? "ghost" : "primary";
}

export function sonarrSearchMissingButtonClass(status) {
  return sonarrMissingScanReady(status) ? "primary" : "ghost";
}

export function sonarrMissingCanCancel(status) {
  if (!status) return false;
  if (status.can_cancel === true) return true;
  const execution = status.execution || {};
  const phase = String(status.phase || "");
  return (
    phase === "searching" ||
    phase === "executing" ||
    Number(execution.queued) > 0 ||
    Number(execution.pending_submit) > 0
  );
}

export function sonarrMissingDisplayPercent(status) {
  if (!status) return null;
  const phase = String(status.phase || "");
  const execution = status.execution;
  if (phase === "executing" && execution && typeof execution.percent === "number") {
    return execution.percent;
  }
  if (typeof status.percent === "number") return status.percent;
  return null;
}

function executionCountLine(execution) {
  if (!execution) return "";
  const bits = [];
  const pending = Number(execution.pending_submit) || 0;
  if (pending) bits.push(`${pending} submitting`);
  bits.push(`${Number(execution.queued) || 0} queued`);
  bits.push(`${Number(execution.running) || 0} running`);
  bits.push(`${Number(execution.completed) || 0} completed`);
  bits.push(`${Number(execution.failed) || 0} failed`);
  const cancelled = Number(execution.cancelled) || 0;
  if (cancelled) bits.push(`${cancelled} cancelled`);
  return bits.join(" · ");
}

export function sonarrMissingProgressLine(status) {
  if (!status) return "";
  const phase = String(status.phase || "idle");
  if (phase === "idle" && !status.result) return "";
  const execution = status.execution;
  const hasCommands =
    execution &&
    (Number(execution.total) > 0 ||
      Number(execution.queued) > 0 ||
      Number(execution.running) > 0 ||
      Number(execution.completed) > 0 ||
      Number(execution.failed) > 0);
  if (hasCommands && (phase === "searching" || phase === "executing" || phase === "searched" || phase === "cancelled")) {
    const bits = [];
    const message = String(status.message || "").trim();
    if (message && !/\d+ queued/.test(message)) bits.push(message);
    bits.push(executionCountLine(execution));
    return bits.filter(Boolean).join(" · ");
  }
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
  if (phase === "searching" && queued) {
    bits.push(`${queued} submitted to Sonarr`);
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

export function sonarrMissingSecondsAgo(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "";
  if (value < 60) return `${Math.round(value)}s since last completion`;
  const minutes = Math.round(value / 60);
  return `${minutes}m since last completion`;
}
