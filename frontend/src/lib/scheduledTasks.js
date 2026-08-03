/** Helpers for the admin Scheduled Tasks page. */

const TASK_LABELS = {
  anniversary_scanner: "Anniversary scanner",
  enthusiast_nudge: "Enthusiast nudges",
  data_retention: "Data retention",
  facet_taxonomy_audit: "Facet taxonomy audit",
  coverage_deficit_audit: "Coverage deficit audit",
  entity_memory_enrichment: "Entity memory enrichment",
  gap_analysis: "Gap analysis",
  health_metrics: "Health metrics",
  llm_logline_enrichment: "LLM logline enrichment",
  metadata_enrichment: "Metadata enrichment",
  plot_neighbors: "Plot neighbors",
  purge_candidates: "Purge candidates",
  recommendation_warmup: "Recommendation warmup",
  semantic_embeddings: "Semantic embeddings",
  summary_motifs: "Summary motifs",
  taste_refresh: "Taste refresh",
  title_relations_refresh: "Title relations refresh",
};

/** Cadence presets for the owner frequency control (seconds). */
export const CADENCE_PRESETS = [
  { label: "1h", seconds: 3600 },
  { label: "6h", seconds: 21600 },
  { label: "12h", seconds: 43200 },
  { label: "1d", seconds: 86400 },
  { label: "7d", seconds: 604800 },
];

/** Tasks that warm Explore rails / Plot Lab / neighbors (fire-and-forget sequence). */
export const WARM_EXPLORE_TASKS = [
  "metadata_enrichment",
  "summary_motifs",
  "plot_neighbors",
  "title_relations_refresh",
  "semantic_embeddings",
];

/** Resolve which Warm Explore tasks exist in the current scheduler list. */
export function resolveWarmExploreTasks(items) {
  const available = new Set((Array.isArray(items) ? items : []).map((t) => t?.name).filter(Boolean));
  return WARM_EXPLORE_TASKS.filter((name) => available.has(name));
}

/** Compact last-run summary already present on list/log payloads. */
export function formatTaskLastRun(task) {
  return formatLastOutcomeLine(task);
}

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

/** Human ETA for trickle backlog / full-pass estimates. */
export function formatEtaDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value === 0) return "caught up";
  if (value < 3600) {
    const mins = Math.max(1, Math.round(value / 60));
    return `~${mins}m`;
  }
  if (value < 86400) {
    const hours = value / 3600;
    const rounded = hours >= 10 ? Math.round(hours) : Math.round(hours * 10) / 10;
    return `~${rounded}h`;
  }
  const days = value / 86400;
  if (days < 14) {
    const rounded = days >= 3 ? Math.round(days) : Math.round(days * 10) / 10;
    return `~${rounded}d`;
  }
  if (days < 60) {
    return `~${Math.round(days)}d`;
  }
  const weeks = days / 7;
  if (weeks < 12) {
    return `~${Math.round(weeks)}w`;
  }
  const months = days / 30;
  return `~${Math.round(months)}mo`;
}

/**
 * Recompute trickle ETA when the owner adjusts cadence locally.
 * Prefers measured items/hour from run history when available and the draft
 * cadence still matches the saved interval; otherwise falls back to theoretical
 * remaining ÷ (items_per_cycle × cycles at draft interval).
 */
export function estimateThroughputEta(progress, intervalSeconds, options = {}) {
  if (!progress) return null;
  const remaining = Number(progress.remaining_items);
  const perCycle = Number(progress.items_per_cycle);
  const interval = Number(intervalSeconds);
  if (!Number.isFinite(remaining) || remaining < 0) return null;
  if (!Number.isFinite(perCycle) || perCycle <= 0) return null;
  if (!Number.isFinite(interval) || interval < 60) return null;
  const cycles = remaining === 0 ? 0 : Math.ceil(remaining / perCycle);
  const savedInterval = Number(options.savedIntervalSeconds ?? interval);
  const measuredIph = Number(progress.items_per_hour);
  const cadenceUnchanged =
    Number.isFinite(savedInterval) && Math.abs(interval - savedInterval) < 1;
  if (
    progress.eta_source === "measured" &&
    cadenceUnchanged &&
    Number.isFinite(measuredIph) &&
    measuredIph > 0
  ) {
    return {
      ...progress,
      estimated_cycles: cycles,
      estimated_seconds: remaining === 0 ? 0 : Math.ceil((remaining / measuredIph) * 3600),
      eta_source: "measured",
      items_per_hour: measuredIph,
    };
  }
  return {
    ...progress,
    estimated_cycles: cycles,
    estimated_seconds: cycles * interval,
    eta_source: "theoretical",
  };
}

/** One-line owner-facing throughput summary. */
export function formatThroughputEstimate(progress) {
  if (!progress) return "";
  const remaining = Number(progress.remaining_items);
  const perCycle = Number(progress.items_per_cycle);
  const eta = formatEtaDuration(progress.estimated_seconds);
  const scope = progress.scope_label || "remaining work";
  if (!Number.isFinite(remaining) || !Number.isFinite(perCycle)) return "";
  if (remaining === 0) {
    return `Caught up — no ${scope} right now.`;
  }
  const cycles = Number(progress.estimated_cycles);
  const cycleBit = Number.isFinite(cycles)
    ? `${cycles} cycle${cycles === 1 ? "" : "s"}`
    : "several cycles";
  const sourceBit = progress.eta_source === "measured" ? " (measured)" : "";
  return (
    `About ${remaining.toLocaleString()} ${scope} · ${perCycle}/run · ` +
    `${cycleBit} ≈ ${eta} at this cadence${sourceBit}`
  );
}

/** Format measured rate payload from the API (items/hour, success rate). */
export function formatMeasuredRate(rate) {
  if (!rate) return "";
  const iph = Number(rate.items_per_hour);
  const success = Number(rate.success_rate);
  const runs = Number(rate.run_count);
  const parts = [];
  if (Number.isFinite(iph) && iph > 0) {
    const rounded = iph >= 10 ? Math.round(iph) : Math.round(iph * 10) / 10;
    parts.push(`${rounded.toLocaleString()}/hr measured`);
  }
  if (Number.isFinite(success) && Number.isFinite(runs) && runs > 0) {
    parts.push(`${Math.round(success * 100)}% success · ${runs} run${runs === 1 ? "" : "s"}`);
  } else if (Number.isFinite(runs) && runs > 0) {
    parts.push(`${runs} run${runs === 1 ? "" : "s"} in window`);
  }
  const p50 = Number(rate.duration_p50_ms);
  const p95 = Number(rate.duration_p95_ms);
  if (Number.isFinite(p50) && Number.isFinite(p95)) {
    parts.push(`p50 ${formatDurationMs(p50)} · p95 ${formatDurationMs(p95)}`);
  }
  return parts.join(" · ");
}

/** Compact recent-run row for the history table. */
export function formatHistoryRunLine(run) {
  if (!run) return "";
  const when = formatEpoch(run.finished_at ?? run.started_at);
  const status = summarizeLastStatus(run.status);
  const duration = formatDurationMs(run.duration_ms);
  const items =
    run.items_processed != null && Number.isFinite(Number(run.items_processed))
      ? `${Number(run.items_processed).toLocaleString()} items`
      : null;
  return [when, status, duration, items].filter(Boolean).join(" · ");
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

/** Human-readable detail for skipped/failed/interrupted outcomes. */
export function formatOutcomeReason(taskOrRun) {
  if (!taskOrRun) return "";
  const reason = String(taskOrRun.outcome_reason || taskOrRun.last_outcome_reason || "").trim();
  if (reason) return reason;
  const summary = taskOrRun.summary;
  if (summary?.outcome_reason) return String(summary.outcome_reason).trim();
  if (summary?.note) return String(summary.note).trim();
  if (summary?.reason) return String(summary.reason).replace(/_/g, " ");
  if (taskOrRun.error) return String(taskOrRun.error).trim();
  return "";
}

/** Prefer the freshest last-run fields exposed by list/log APIs. */
export function resolveLastOutcome(task) {
  if (!task) {
    return { status: null, reason: "", summaryLine: "", when: null, metrics: {} };
  }
  const status = task.last_status ?? task.status ?? null;
  const when = task.last_finished_at ?? task.finished_at ?? task.last_run_at ?? null;
  const summaryLine = formatRunSummaryLine(task);
  return {
    status,
    reason: formatOutcomeReason(task),
    summaryLine,
    when,
    metrics: resolveRunMetrics(task),
  };
}

/** Structured counters from the last run, when available. */
export function resolveRunMetrics(taskOrRun) {
  const summary = taskOrRun?.last_run_summary || taskOrRun?.summary;
  if (summary?.metrics && typeof summary.metrics === "object") {
    return summary.metrics;
  }
  if (taskOrRun?.metrics && typeof taskOrRun.metrics === "object") {
    return taskOrRun.metrics;
  }
  return {};
}

/** One-line impact summary for list rows and monitor footer. */
export function formatRunSummaryLine(taskOrRun) {
  if (!taskOrRun) return "";
  const direct = String(
    taskOrRun.last_run_summary_line || taskOrRun.summary_line || "",
  ).trim();
  if (direct) return direct;
  const summary = taskOrRun.last_run_summary || taskOrRun.summary;
  if (summary?.summary_line) return String(summary.summary_line).trim();
  const status = String(taskOrRun.last_status || taskOrRun.status || "");
  if (status === "skipped" || status.startsWith("error")) {
    return formatOutcomeReason(taskOrRun);
  }
  return "";
}

/** Secondary line under LAST RUN — summary metrics, skip reason, or started time. */
export function formatTaskLastRunDetail(task) {
  if (!task) return "";
  if (isTaskRunning(task)) return "";
  const summaryLine = formatRunSummaryLine(task);
  if (summaryLine) return summaryLine;
  if (task.last_started_at) {
    return `Started ${formatEpoch(task.last_started_at)}`;
  }
  return "";
}

export function formatLastOutcomeLine(task) {
  const { status, reason, when } = resolveLastOutcome(task);
  const label = summarizeLastStatus(status);
  if (label === "Never run") return "Never run";
  const whenText = when != null && when !== "" ? formatEpoch(when) : null;
  const base = whenText ? `${label} · ${whenText}` : label;
  if ((status === "skipped" || String(status || "").startsWith("error")) && reason) {
    return `${base} — ${reason}`;
  }
  return base;
}

export function isTaskRunning(task) {
  return Boolean(task?.running || task?.current_run);
}

export function taskRowTone(task) {
  if (isTaskRunning(task)) return "running";
  if (task?.quarantine?.is_quarantined) return "quarantined";
  const status = String(task?.last_status || "");
  if (status.startsWith("error")) return "error";
  if (status === "skipped") return "skipped";
  if (!task?.enabled) return "disabled";
  if (task?.overdue) return "overdue";
  return "ok";
}

export function formatLogLine(event) {
  if (!event) return "";
  const time = formatEpoch(event.ts);
  const level = String(event.level || "info").toUpperCase();
  const data = event.data || {};
  const summaryLine = String(data.summary_line || "").trim();
  const reason = formatOutcomeReason(data);
  const base = `[${time}] ${level}  ${event.message || ""}`;
  const extra = summaryLine || reason;
  if (extra && !String(event.message || "").includes(extra)) {
    return `${base} — ${extra}`;
  }
  return base;
}

/**
 * Sort key for "what's next": running / due-now first, then soonest next_run_at,
 * then later upcoming. Disabled tasks (no next run) sort last.
 */
export function resolveNextRunAt(task, now = Date.now() / 1000) {
  if (!task || task.enabled === false) return null;
  if (isTaskRunning(task)) return Number(now);
  const next = Number(task.next_run_at);
  if (Number.isFinite(next)) return next;
  // Never run (or missing next) while enabled → due immediately.
  return Number(now);
}

/** Ascending by next fire time; disabled last. Stable by name. */
export function compareTasksByNextRun(a, b, now = Date.now() / 1000) {
  const aEnabled = a?.enabled !== false;
  const bEnabled = b?.enabled !== false;
  if (aEnabled !== bEnabled) return aEnabled ? -1 : 1;

  const aRunning = isTaskRunning(a);
  const bRunning = isTaskRunning(b);
  if (aRunning !== bRunning) return aRunning ? -1 : 1;

  const aNext = resolveNextRunAt(a, now);
  const bNext = resolveNextRunAt(b, now);
  const aKey = aNext == null ? Number.POSITIVE_INFINITY : aNext;
  const bKey = bNext == null ? Number.POSITIVE_INFINITY : bNext;
  if (aKey !== bKey) return aKey - bKey;

  const aName = String(a?.name || "");
  const bName = String(b?.name || "");
  return aName.localeCompare(bName);
}

export function sortTasksByNextRun(items, now = Date.now() / 1000) {
  const list = Array.isArray(items) ? [...items] : [];
  list.sort((a, b) => compareTasksByNextRun(a, b, now));
  return list;
}

/**
 * Load contribution at the current cadence: last duration ÷ interval.
 * Higher = heavier share of idle wall-clock (duty cycle). Returns 0 when
 * duration or interval is missing/invalid.
 */
export function taskLoadScore(task) {
  if (!task) return 0;
  const durationMs = Number(task.last_duration_ms);
  const interval = Number(task.run_interval_seconds);
  if (!Number.isFinite(durationMs) || durationMs < 0) return 0;
  if (!Number.isFinite(interval) || interval <= 0) return 0;
  return durationMs / 1000 / interval;
}

/** Descending by duty cycle (heaviest first); disabled last. Stable by name. */
export function compareTasksByLoad(a, b) {
  const aEnabled = a?.enabled !== false;
  const bEnabled = b?.enabled !== false;
  if (aEnabled !== bEnabled) return aEnabled ? -1 : 1;

  const aScore = taskLoadScore(a);
  const bScore = taskLoadScore(b);
  if (aScore !== bScore) return bScore - aScore;

  const aDuration = Number(a?.last_duration_ms);
  const bDuration = Number(b?.last_duration_ms);
  const aDur = Number.isFinite(aDuration) ? aDuration : -1;
  const bDur = Number.isFinite(bDuration) ? bDuration : -1;
  if (aDur !== bDur) return bDur - aDur;

  const aName = String(a?.name || "");
  const bName = String(b?.name || "");
  return aName.localeCompare(bName);
}

export function sortTasksByLoad(items) {
  const list = Array.isArray(items) ? [...items] : [];
  list.sort((a, b) => compareTasksByLoad(a, b));
  return list;
}

export const TASK_SORT_MODES = Object.freeze({
  next_run: "next_run",
  heaviest: "heaviest",
});

export const TASK_SORT_STORAGE_KEY = "projectionist.scheduledTasks.sort";

export function sortScheduledTasks(items, mode, now = Date.now() / 1000) {
  if (mode === TASK_SORT_MODES.heaviest) {
    return sortTasksByLoad(items);
  }
  return sortTasksByNextRun(items, now);
}

/** Owner-facing next-run label for list rows. */
export function formatTaskNextRun(task, now = Date.now() / 1000) {
  if (!task) return "—";
  if (!task.enabled) return "—";
  if (isTaskRunning(task)) return "Running now";
  const next = Number(task.next_run_at);
  if (Number.isFinite(next)) {
    if (next <= now || task.overdue) return "Due now";
    return formatEpoch(next);
  }
  if (task.overdue || task.last_run_at == null) return "Due now";
  return "—";
}

/** Compact unified execution-log row (cross-task history). */
export function formatExecutionLogLine(run) {
  if (!run) return "";
  const name = taskDisplayName(run.name);
  const status = String(run.status || "") === "running"
    ? "Running"
    : summarizeLastStatus(run.status);
  const started = formatEpoch(run.started_at);
  const finished =
    run.finished_at != null && run.finished_at !== ""
      ? formatEpoch(run.finished_at)
      : "—";
  const duration = formatDurationMs(run.duration_ms);
  const summary =
    formatRunSummaryLine(run) ||
    formatOutcomeReason(run) ||
    (run.error ? String(run.error).trim() : "");
  const base = `${name} · ${status} · ${started} → ${finished} · ${duration}`;
  return summary ? `${base} — ${summary}` : base;
}

/** Merge in-flight current_run ahead of durable history (newest first). */
export function mergeExecutionLogRuns(historyRuns, currentRun) {
  const runs = Array.isArray(historyRuns) ? [...historyRuns] : [];
  if (!currentRun || !currentRun.name) return runs;
  const currentId = String(currentRun.id || `running:${currentRun.name}`);
  const filtered = runs.filter((run) => String(run?.id) !== currentId);
  return [{ ...currentRun, id: currentId, status: currentRun.status || "running" }, ...filtered];
}
