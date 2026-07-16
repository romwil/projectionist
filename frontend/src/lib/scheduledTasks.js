/** Helpers for the admin Scheduled Tasks page. */

const TASK_LABELS = {
  anniversary_scanner: "Anniversary scanner",
  data_retention: "Data retention",
  gap_analysis: "Gap analysis",
  health_metrics: "Health metrics",
  llm_logline_enrichment: "LLM logline enrichment",
  llm_theme_tagging: "LLM theme tagging",
  metadata_enrichment: "Metadata enrichment",
  plot_neighbors: "Plot neighbors",
  purge_candidates: "Purge candidates",
  recommendation_warmup: "Recommendation warmup",
  semantic_embeddings: "Semantic embeddings",
  summary_motifs: "Summary motifs",
  taste_refresh: "Taste refresh",
  title_relations_refresh: "Title relations refresh",
};

export function taskDisplayName(name) {
  if (!name) return "Unknown task";
  if (TASK_LABELS[name]) return TASK_LABELS[name];
  return String(name)
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatInterval(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "—";
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) {
    const mins = Math.round(value / 60);
    return `${mins}m`;
  }
  if (value < 86400) {
    const hours = value / 3600;
    return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`;
  }
  const days = value / 86400;
  return Number.isInteger(days) ? `${days}d` : `${days.toFixed(1)}d`;
}

export function formatDurationMs(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 1000) return `${Math.round(value)}ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(1)}s`;
  const mins = Math.floor(value / 60_000);
  const secs = Math.round((value % 60_000) / 1000);
  return secs ? `${mins}m ${secs}s` : `${mins}m`;
}

export function formatEpoch(ts) {
  if (ts == null || ts === "") return "—";
  const ms = typeof ts === "number" ? ts * 1000 : Date.parse(ts);
  if (!Number.isFinite(ms)) return "—";
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return "—";
  }
}

export function summarizeLastStatus(status) {
  if (!status) return "Never run";
  const text = String(status);
  if (text.startsWith("error")) return "Failed";
  if (text === "interrupted") return "Interrupted";
  if (text === "skipped") return "Skipped";
  if (text === "completed") return "Succeeded";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function isTaskRunning(task) {
  return Boolean(task?.running || task?.current_run);
}

export function taskRowTone(task) {
  if (isTaskRunning(task)) return "running";
  if (task?.quarantine?.is_quarantined) return "quarantined";
  const status = String(task?.last_status || "");
  if (status.startsWith("error")) return "error";
  if (!task?.enabled) return "disabled";
  if (task?.overdue) return "overdue";
  return "ok";
}

export function formatLogLine(event) {
  if (!event) return "";
  const time = formatEpoch(event.ts);
  const level = String(event.level || "info").toUpperCase();
  return `[${time}] ${level}  ${event.message || ""}`;
}
