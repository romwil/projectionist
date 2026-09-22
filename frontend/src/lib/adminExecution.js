/** Shared copy helpers for Sonarr-style admin execution snapshots. */

export const ADMIN_PHASE_LABELS = {
  idle: "Ready",
  queued: "Queued",
  preparing: "Preparing",
  registering: "Registering",
  sending: "Sending",
  generating: "Generating",
  running: "Working",
  scanning: "Scanning",
  comparing: "Comparing",
  searching: "Submitting",
  executing: "Running",
  done: "Finished",
  searched: "Searches finished",
  cancelled: "Cancelled",
  error: "Failed",
};

export function adminPhaseLabel(phase, extraLabels = {}) {
  const key = String(phase || "").trim().toLowerCase();
  return extraLabels[key] || ADMIN_PHASE_LABELS[key] || "Working";
}

export function adminCanCancel(job) {
  if (!job) return false;
  if (job.can_cancel === true) return true;
  const execution = job.execution || {};
  const phase = String(job.phase || "");
  return Boolean(
    job.busy &&
      (Number(execution.queued) > 0 ||
        Number(execution.pending_submit) > 0 ||
        ["queued", "registering", "sending", "generating", "running"].includes(phase)),
  );
}

export function adminDisplayPercent(job) {
  if (!job) return null;
  const execution = job.execution;
  if (job.busy && execution && typeof execution.percent === "number") {
    return Math.min(99, execution.percent);
  }
  if (typeof job.percent === "number") return job.percent;
  return null;
}

export function adminExecutionCountLine(execution) {
  if (!execution) return "";
  const bits = [];
  const pending = Number(execution.pending_submit) || 0;
  if (pending && pending !== (Number(execution.queued) || 0)) {
    bits.push(`${pending} submitting`);
  }
  bits.push(`${Number(execution.queued) || 0} queued`);
  bits.push(`${Number(execution.running) || 0} running`);
  bits.push(`${Number(execution.completed) || 0} completed`);
  const skipped = Number(execution.skipped) || 0;
  if (skipped) bits.push(`${skipped} skipped`);
  bits.push(`${Number(execution.failed) || 0} failed`);
  const cancelled = Number(execution.cancelled) || 0;
  if (cancelled) bits.push(`${cancelled} cancelled`);
  return bits.join(" · ");
}

export function adminProgressLine(job) {
  if (!job) return "";
  const phase = String(job.phase || "idle");
  if (phase === "idle" && !job.result && !(job.items || []).length) return "";
  const execution = job.execution;
  const hasWork =
    execution &&
    (Number(execution.total) > 0 ||
      Number(execution.queued) > 0 ||
      Number(execution.running) > 0 ||
      Number(execution.completed) > 0 ||
      Number(execution.failed) > 0 ||
      Number(execution.skipped) > 0);
  const bits = [];
  const message = String(job.message || "").trim();
  if (message && !/\d+ queued/.test(message)) bits.push(message);
  if (hasWork) bits.push(adminExecutionCountLine(execution));
  else if (message && !bits.includes(message)) bits.push(message);
  return bits.filter(Boolean).join(" · ");
}

export function adminItemStatusLabel(item) {
  const outcome = String(item?.outcome || "").trim();
  const status = String(item?.status || "queued").trim();
  if (outcome === "registered") return "registered";
  if (outcome === "already") return "already in Radarr";
  if (outcome === "path_conflict") return "path conflict";
  if (outcome === "delivered") return "delivered";
  if (outcome === "skipped") return "skipped";
  if (outcome === "built" || outcome === "ready") return "done";
  if (outcome === "empty") return "empty";
  if (status === "skipped") return "already in Radarr";
  if (status === "running") return "in flight";
  if (status === "completed") return "done";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "cancelled";
  return "queued";
}

export function adminShouldShowCard(job) {
  if (!job) return false;
  const phase = String(job.phase || "idle");
  if (phase !== "idle") return true;
  if (job.result) return true;
  if (Array.isArray(job.items) && job.items.length) return true;
  return Boolean(job.message && job.message !== "Ready when you are");
}

export function adminSecondsAgo(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "";
  if (value < 60) return `${Math.round(value)}s since last completion`;
  return `${Math.round(value / 60)}m since last completion`;
}
