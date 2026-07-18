import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getScheduledTaskHistory,
  getScheduledTaskLog,
  listScheduledTasks,
  resetScheduledTaskQuarantine,
  runScheduledTask,
  updateScheduledTask,
} from "../api/client";
import KnowledgeCoverageCard from "../components/KnowledgeCoverageCard";
import {
  CADENCE_PRESETS,
  estimateThroughputEta,
  formatDurationMs,
  formatEpoch,
  formatHistoryRunLine,
  formatInterval,
  formatLastOutcomeLine,
  formatLogLine,
  formatMeasuredRate,
  formatThroughputEstimate,
  formatTaskLastRun,
  formatTaskLastRunDetail,
  isTaskRunning,
  resolveLastOutcome,
  resolveWarmExploreTasks,
  summarizeLastStatus,
  taskDisplayName,
  taskRowTone,
} from "../lib/scheduledTasks.js";

const POLL_IDLE_MS = 5000;
const POLL_ACTIVE_MS = 1200;
const MIN_INTERVAL_SECONDS = 60;
const MAX_INTERVAL_SECONDS = 30 * 86400;

export default function ScheduledTasksPage() {
  const [items, setItems] = useState([]);
  const [idle, setIdle] = useState(false);
  const [running, setRunning] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [selectedName, setSelectedName] = useState(null);
  const [events, setEvents] = useState([]);
  const [latestSeq, setLatestSeq] = useState(0);
  const [currentRun, setCurrentRun] = useState(null);
  const [lastRun, setLastRun] = useState(null);
  const [busyNames, setBusyNames] = useState(() => new Set());
  const [warmStatus, setWarmStatus] = useState("");
  const [warming, setWarming] = useState(false);
  const [optimisticStart, setOptimisticStart] = useState(null);
  const [draftInterval, setDraftInterval] = useState(null);
  const [customHours, setCustomHours] = useState("");
  const [draftBatch, setDraftBatch] = useState(null);
  const [historyRuns, setHistoryRuns] = useState([]);
  const logEndRef = useRef(null);
  const latestSeqRef = useRef(0);
  const warmExploreNames = useMemo(() => resolveWarmExploreTasks(items), [items]);

  const selected = useMemo(
    () => items.find((item) => item.name === selectedName) || null,
    [items, selectedName],
  );

  useEffect(() => {
    if (!selected) {
      setDraftInterval(null);
      setCustomHours("");
      setDraftBatch(null);
      return;
    }
    const seconds = Number(selected.run_interval_seconds) || MIN_INTERVAL_SECONDS;
    setDraftInterval(seconds);
    const preset = CADENCE_PRESETS.some((item) => item.seconds === seconds);
    setCustomHours(preset ? "" : String(Math.round((seconds / 3600) * 100) / 100));
    setDraftBatch(
      selected.items_per_cycle != null ? Number(selected.items_per_cycle) : null,
    );
  }, [selectedName, selected?.run_interval_seconds, selected?.items_per_cycle]);

  const liveProgress = useMemo(
    () =>
      estimateThroughputEta(
        selected?.progress,
        draftInterval ?? selected?.run_interval_seconds,
        { savedIntervalSeconds: selected?.run_interval_seconds },
      ),
    [selected?.progress, draftInterval, selected?.run_interval_seconds],
  );

  const cadenceDirty =
    selected != null &&
    draftInterval != null &&
    Number(draftInterval) !== Number(selected.run_interval_seconds);

  const batchDirty =
    selected != null &&
    selected.items_per_cycle != null &&
    draftBatch != null &&
    Number(draftBatch) !== Number(selected.items_per_cycle);

  const selectedOutcome = useMemo(() => {
    if (!selected && !lastRun) {
      return { status: null, reason: "", summaryLine: "", when: null, metrics: {} };
    }
    const merged = {
      ...(selected || {}),
      ...(lastRun
        ? {
            last_status: lastRun.status ?? selected?.last_status,
            last_finished_at: lastRun.finished_at ?? selected?.last_finished_at,
            last_outcome_reason: lastRun.outcome_reason ?? selected?.last_outcome_reason,
            last_run_summary_line: lastRun.summary_line,
            last_run_summary: {
              summary_line: lastRun.summary_line,
              metrics: lastRun.metrics,
              outcome_reason: lastRun.outcome_reason,
              status: lastRun.status,
            },
          }
        : {}),
    };
    return resolveLastOutcome(merged);
  }, [lastRun, selected]);

  const refreshList = useCallback(async () => {
    try {
      const data = await listScheduledTasks();
      setItems(data.items || []);
      setIdle(Boolean(data.idle));
      setRunning(data.running || null);
      setError("");
      setSelectedName((current) => {
        if (current && (data.items || []).some((item) => item.name === current)) {
          return current;
        }
        const firstRunning = (data.items || []).find((item) => item.running);
        return firstRunning?.name || (data.items || [])[0]?.name || null;
      });
    } catch (err) {
      setError(err.message || "Failed to load scheduled tasks");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLog = useCallback(
    async ({ reset = false } = {}) => {
      if (!selectedName) return;
      try {
        const after = reset ? 0 : latestSeqRef.current;
        const data = await getScheduledTaskLog(selectedName, {
          after_seq: after,
          limit: 300,
        });
        const nextEvents = data.events || [];
        if (reset) {
          setEvents(nextEvents);
        } else if (nextEvents.length) {
          setEvents((prev) => {
            const seen = new Set(prev.map((event) => event.seq));
            const merged = [...prev];
            for (const event of nextEvents) {
              if (!seen.has(event.seq)) merged.push(event);
            }
            return merged.slice(-400);
          });
        }
        if (typeof data.latest_seq === "number") {
          latestSeqRef.current = data.latest_seq;
          setLatestSeq(data.latest_seq);
        }
        setCurrentRun(data.current_run || null);
        setLastRun(data.last_run || null);
        if (data.running !== undefined) {
          setRunning(data.running || null);
        }
      } catch (err) {
        setActionError(err.message || "Failed to load task log");
      }
    },
    [selectedName],
  );

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  useEffect(() => {
    latestSeqRef.current = 0;
    setEvents([]);
    setLatestSeq(0);
    setCurrentRun(null);
    setLastRun(null);
    setOptimisticStart(null);
    setHistoryRuns([]);
    if (selectedName) {
      refreshLog({ reset: true });
      getScheduledTaskHistory(selectedName, { limit: 12 })
        .then((data) => setHistoryRuns(data.runs || []))
        .catch(() => setHistoryRuns([]));
    }
  }, [selectedName, refreshLog]);

  // Drop the optimistic "Started" line once a real start event lands for this task.
  useEffect(() => {
    if (!optimisticStart) return;
    const hasRealStart = events.some(
      (event) =>
        event.task === optimisticStart.task &&
        String(event.message || "").startsWith("Started"),
    );
    const startedAfter =
      currentRun &&
      currentRun.task === optimisticStart.task &&
      Number(currentRun.started_at) >= optimisticStart.ts - 5;
    if (hasRealStart || startedAfter) {
      setOptimisticStart(null);
    }
  }, [events, currentRun, optimisticStart]);

  // Synthetic log lines shown immediately after Run now, or when a running task
  // is selected before its first real event has been polled.
  const displayEvents = useMemo(() => {
    const hasStart = events.some((event) =>
      String(event.message || "").startsWith("Started"),
    );
    if (hasStart) return events;
    const synthetic = [];
    if (optimisticStart && optimisticStart.task === selectedName) {
      synthetic.push({
        seq: -1,
        ts: optimisticStart.ts,
        task: optimisticStart.task,
        level: "status",
        message: "Started (manual)",
        optimistic: true,
      });
    } else if (
      currentRun &&
      currentRun.task === selectedName &&
      !events.length
    ) {
      synthetic.push({
        seq: -1,
        ts: currentRun.started_at,
        task: currentRun.task,
        level: "status",
        message: `Started (${currentRun.trigger || "schedule"})`,
        optimistic: true,
      });
    }
    return [...synthetic, ...events];
  }, [events, optimisticStart, currentRun, selectedName]);

  useEffect(() => {
    const active = Boolean(running) || Boolean(currentRun);
    const delay = active ? POLL_ACTIVE_MS : POLL_IDLE_MS;
    const timer = setInterval(() => {
      refreshList();
      refreshLog();
    }, delay);
    return () => clearInterval(timer);
  }, [running, currentRun, refreshList, refreshLog]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [displayEvents]);

  async function withBusy(name, fn) {
    setBusyNames((prev) => new Set(prev).add(name));
    setActionError("");
    try {
      await fn();
      await refreshList();
      await refreshLog({ reset: false });
      if (name === selectedName) {
        try {
          const data = await getScheduledTaskHistory(name, { limit: 12 });
          setHistoryRuns(data.runs || []);
        } catch {
          /* keep prior history */
        }
      }
    } catch (err) {
      setActionError(err.message || "Action failed");
    } finally {
      setBusyNames((prev) => {
        const next = new Set(prev);
        next.delete(name);
        return next;
      });
    }
  }

  function handleSelect(name) {
    setSelectedName(name);
  }

  function handleRun(name) {
    setSelectedName(name);
    setOptimisticStart({ task: name, ts: Date.now() / 1000 });
    return withBusy(name, async () => {
      await runScheduledTask(name);
      await refreshLog({ reset: true });
    });
  }

  function handleToggleEnabled(task) {
    return withBusy(task.name, async () => {
      await updateScheduledTask(task.name, { enabled: !task.enabled });
    });
  }

  function clampInterval(seconds) {
    const value = Math.round(Number(seconds));
    if (!Number.isFinite(value)) return MIN_INTERVAL_SECONDS;
    return Math.min(MAX_INTERVAL_SECONDS, Math.max(MIN_INTERVAL_SECONDS, value));
  }

  function handleCadencePreset(seconds) {
    setDraftInterval(clampInterval(seconds));
    setCustomHours("");
  }

  function handleCustomHoursChange(value) {
    setCustomHours(value);
    const hours = Number(value);
    if (!Number.isFinite(hours) || hours <= 0) return;
    setDraftInterval(clampInterval(hours * 3600));
  }

  function handleSaveCadence() {
    if (!selected || draftInterval == null) return;
    const next = clampInterval(draftInterval);
    return withBusy(selected.name, async () => {
      await updateScheduledTask(selected.name, { run_interval_seconds: next });
    });
  }

  function handleResetCadence() {
    if (!selected) return;
    const fallback =
      Number(selected.default_run_interval_seconds) ||
      Number(selected.run_interval_seconds) ||
      MIN_INTERVAL_SECONDS;
    setDraftInterval(clampInterval(fallback));
    setCustomHours("");
  }

  function handleSaveBatch() {
    if (!selected || draftBatch == null) return;
    const next = Math.max(1, Math.min(500, Math.round(Number(draftBatch))));
    return withBusy(selected.name, async () => {
      await updateScheduledTask(selected.name, { items_per_cycle: next });
    });
  }

  function handleResetBatch() {
    if (!selected) return;
    const fallback =
      selected.default_items_per_cycle != null
        ? Number(selected.default_items_per_cycle)
        : Number(selected.items_per_cycle);
    if (Number.isFinite(fallback)) setDraftBatch(fallback);
  }

  function handleResetQuarantine(name) {
    return withBusy(name, async () => {
      await resetScheduledTaskQuarantine(name);
    });
  }

  async function handleWarmExplore() {
    if (warming || !warmExploreNames.length || running) return;
    setWarming(true);
    setActionError("");
    setWarmStatus("Starting Warm Explore…");
    const started = [];
    try {
      for (const name of warmExploreNames) {
        await runScheduledTask(name);
        started.push(taskDisplayName(name));
        setWarmStatus(`Triggered ${started.join(", ")}`);
        // Brief gap so the scheduler can accept the next fire-and-forget run.
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      setWarmStatus(`Warm Explore queued: ${started.join(", ")}`);
      await refreshList();
    } catch (err) {
      setActionError(err.message || "Warm Explore failed");
      setWarmStatus("");
    } finally {
      setWarming(false);
    }
  }

  return (
    <div className="scheduled-tasks-page" data-testid="scheduled-tasks-page">
      <header className="dash-header">
        <div>
          <p className="eyebrow">Admin</p>
          <h2 className="dash-title">Scheduled Tasks</h2>
          <p className="status status-secondary">
            Idle scheduler {idle ? "is idle" : "is waiting for idle"}
            {running ? ` · running ${taskDisplayName(running)}` : ""}
          </p>
          {warmStatus ? (
            <p className="status status-secondary" data-testid="warm-explore-status">
              {warmStatus}
            </p>
          ) : null}
        </div>
        <div className="scheduled-tasks-header-actions">
          <button
            type="button"
            className="ghost"
            data-testid="warm-explore-preset"
            disabled={warming || !warmExploreNames.length || Boolean(running)}
            title={
              warmExploreNames.length
                ? `Runs: ${warmExploreNames.map(taskDisplayName).join(", ")}`
                : "No Warm Explore tasks available"
            }
            onClick={handleWarmExplore}
          >
            {warming ? "Warming…" : "Warm Explore"}
          </button>
          <button type="button" className="ghost" onClick={() => refreshList()} data-testid="tasks-refresh">
            Refresh
          </button>
        </div>
      </header>

      {error ? <p className="dash-panel-error" data-testid="tasks-error">{error}</p> : null}
      {actionError ? (
        <p className="dash-panel-error" data-testid="tasks-action-error">
          {actionError}
        </p>
      ) : null}

      <KnowledgeCoverageCard variant="strip" className="scheduled-tasks-coverage" />

      {loading ? (
        <p className="status status-secondary">Loading tasks…</p>
      ) : (
        <div className="scheduled-tasks-layout">
          <section className="dash-panel scheduled-tasks-list-panel">
            <h3 className="dash-panel-title">All tasks</h3>
            <div className="user-management-table-wrap">
              <table className="user-management-table" data-testid="scheduled-tasks-table">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Cadence</th>
                    <th>Status</th>
                    <th>Last run</th>
                    <th>Duration</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((task) => {
                    const tone = taskRowTone(task);
                    const selectedRow = task.name === selectedName;
                    const busy = busyNames.has(task.name);
                    return (
                      <tr
                        key={task.name}
                        className={`scheduled-task-row tone-${tone}${selectedRow ? " is-selected" : ""}`}
                        data-testid={`scheduled-task-row-${task.name}`}
                        onClick={() => handleSelect(task.name)}
                      >
                        <td>
                          <div className="scheduled-task-name">{taskDisplayName(task.name)}</div>
                          <div className="scheduled-task-id">{task.name}</div>
                        </td>
                        <td>{formatInterval(task.run_interval_seconds)}</td>
                        <td>
                          <span className={`scheduled-task-pill tone-${tone}`}>
                            {isTaskRunning(task)
                              ? "Running"
                              : task.quarantine?.is_quarantined
                                ? "Quarantined"
                                : task.enabled
                                  ? summarizeLastStatus(task.last_status)
                                  : "Disabled"}
                          </span>
                        </td>
                        <td data-testid={`task-last-run-${task.name}`}>
                          <div>{formatTaskLastRun(task)}</div>
                          {formatTaskLastRunDetail(task) ? (
                            <div
                              className="scheduled-task-meta"
                              title={formatTaskLastRunDetail(task)}
                            >
                              {formatTaskLastRunDetail(task)}
                            </div>
                          ) : null}
                        </td>
                        <td>{formatDurationMs(task.last_duration_ms)}</td>
                        <td>
                          <div className="user-management-actions" onClick={(event) => event.stopPropagation()}>
                            <button
                              type="button"
                              className="ghost"
                              disabled={busy || isTaskRunning(task) || Boolean(running)}
                              data-testid={`run-task-${task.name}`}
                              onClick={() => handleRun(task.name)}
                            >
                              Run now
                            </button>
                            <button
                              type="button"
                              className="ghost"
                              disabled={busy}
                              data-testid={`toggle-task-${task.name}`}
                              onClick={() => handleToggleEnabled(task)}
                            >
                              {task.enabled ? "Disable" : "Enable"}
                            </button>
                            {task.quarantine?.is_quarantined ? (
                              <button
                                type="button"
                                className="ghost"
                                disabled={busy}
                                data-testid={`reset-task-${task.name}`}
                                onClick={() => handleResetQuarantine(task.name)}
                              >
                                Reset
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="dash-panel scheduled-tasks-monitor" data-testid="task-monitor-panel">
            <div className="scheduled-tasks-monitor-header">
              <div>
                <h3 className="dash-panel-title">
                  {selected ? taskDisplayName(selected.name) : "Monitor"}
                </h3>
                <p className="status status-secondary">
                  {currentRun
                    ? `Running · started ${formatEpoch(currentRun.started_at)} · ${formatDurationMs(currentRun.elapsed_ms)}`
                    : selectedOutcome.status
                      ? formatLastOutcomeLine(
                          lastRun || {
                            ...selected,
                            last_status: selectedOutcome.status,
                            last_finished_at: selectedOutcome.when,
                            last_outcome_reason: selectedOutcome.reason,
                          },
                        )
                      : "Select a task to monitor output"}
                </p>
                {selected?.description ? (
                  <p
                    className="scheduled-task-description"
                    data-testid="task-description"
                  >
                    {selected.description}
                  </p>
                ) : null}
                {!currentRun && selectedOutcome.summaryLine ? (
                  <p className="scheduled-task-meta" data-testid="task-last-summary">
                    {selectedOutcome.summaryLine}
                  </p>
                ) : null}
                {!currentRun && selected ? (
                  <p className="scheduled-task-meta">
                    Run now starts immediately. Skipped means nothing to do or a precondition
                    failed — see the reason in the log below.
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="ghost"
                disabled={!selectedName}
                data-testid="task-log-refresh"
                onClick={() => refreshLog({ reset: true })}
              >
                Refresh log
              </button>
            </div>

            {selected ? (
              <div className="scheduled-task-cadence" data-testid="task-cadence-panel">
                <div className="scheduled-task-cadence-header">
                  <h4 className="scheduled-task-cadence-title">Frequency</h4>
                  <span className="scheduled-task-meta">
                    Current {formatInterval(selected.run_interval_seconds)}
                    {cadenceDirty
                      ? ` · draft ${formatInterval(draftInterval)}`
                      : ""}
                  </span>
                </div>
                <div
                  className="scheduled-task-cadence-presets"
                  role="group"
                  aria-label="Cadence presets"
                >
                  {CADENCE_PRESETS.map((preset) => {
                    const active = Number(draftInterval) === preset.seconds;
                    return (
                      <button
                        key={preset.seconds}
                        type="button"
                        className={`ghost scheduled-task-cadence-preset${active ? " is-active" : ""}`}
                        data-testid={`cadence-preset-${preset.label}`}
                        disabled={busyNames.has(selected.name)}
                        onClick={() => handleCadencePreset(preset.seconds)}
                      >
                        {preset.label}
                      </button>
                    );
                  })}
                </div>
                <div className="scheduled-task-cadence-custom">
                  <label htmlFor="task-cadence-hours">
                    Custom hours
                    <input
                      id="task-cadence-hours"
                      type="number"
                      min="0.02"
                      max="720"
                      step="0.25"
                      inputMode="decimal"
                      value={customHours}
                      data-testid="cadence-custom-hours"
                      disabled={busyNames.has(selected.name)}
                      onChange={(event) => handleCustomHoursChange(event.target.value)}
                      placeholder="e.g. 3"
                    />
                  </label>
                  <div className="scheduled-task-cadence-actions">
                    <button
                      type="button"
                      className="ghost"
                      data-testid="cadence-reset"
                      disabled={busyNames.has(selected.name)}
                      onClick={handleResetCadence}
                    >
                      Reset default
                    </button>
                    <button
                      type="button"
                      data-testid="cadence-save"
                      disabled={
                        busyNames.has(selected.name) || !cadenceDirty || draftInterval == null
                      }
                      onClick={handleSaveCadence}
                    >
                      Save frequency
                    </button>
                  </div>
                </div>
                {liveProgress ? (
                  <p
                    className="scheduled-task-throughput"
                    data-testid="task-throughput-estimate"
                  >
                    {formatThroughputEstimate(liveProgress)}
                  </p>
                ) : null}
                {selected.rate && formatMeasuredRate(selected.rate) ? (
                  <p
                    className="scheduled-task-measured-rate"
                    data-testid="task-measured-rate"
                  >
                    {formatMeasuredRate(selected.rate)}
                  </p>
                ) : null}
                {selected.items_per_cycle != null ? (
                  <div className="scheduled-task-batch" data-testid="task-batch-panel">
                    <label htmlFor="task-batch-size">
                      Items per run
                      <input
                        id="task-batch-size"
                        type="number"
                        min="1"
                        max="500"
                        step="1"
                        value={draftBatch ?? ""}
                        data-testid="batch-size-input"
                        disabled={busyNames.has(selected.name)}
                        onChange={(event) => {
                          const value = Number(event.target.value);
                          if (Number.isFinite(value)) setDraftBatch(value);
                          else setDraftBatch(null);
                        }}
                      />
                    </label>
                    <div className="scheduled-task-cadence-actions">
                      <button
                        type="button"
                        className="ghost"
                        data-testid="batch-reset"
                        disabled={busyNames.has(selected.name)}
                        onClick={handleResetBatch}
                      >
                        Reset default
                      </button>
                      <button
                        type="button"
                        data-testid="batch-save"
                        disabled={
                          busyNames.has(selected.name) || !batchDirty || draftBatch == null
                        }
                        onClick={handleSaveBatch}
                      >
                        Save batch
                      </button>
                    </div>
                    {selected.autotune_enabled ? (
                      <p className="scheduled-task-meta">
                        Auto-tune adjusts batch/interval after successful runs within safety
                        caps. Your saved values stick until the next tune or manual edit.
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {historyRuns.length ? (
                  <div
                    className="scheduled-task-history"
                    data-testid="task-run-history"
                  >
                    <h4 className="scheduled-task-cadence-title">Recent runs</h4>
                    <ul className="scheduled-task-history-list">
                      {historyRuns.slice(0, 8).map((run) => (
                        <li
                          key={run.id}
                          className="scheduled-task-history-item"
                          data-testid={`task-history-row-${run.id}`}
                        >
                          {formatHistoryRunLine(run)}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="scheduled-tasks-log" data-testid="task-log">
              {displayEvents.length ? (
                displayEvents.map((event) => (
                  <div
                    key={`${event.seq}-${event.ts}`}
                    className={`scheduled-tasks-log-line level-${event.level || "info"}${
                      event.optimistic ? " is-optimistic" : ""
                    }`}
                    data-testid={`task-log-line-${event.seq}`}
                  >
                    {formatLogLine(event)}
                  </div>
                ))
              ) : (
                <p className="dash-empty">
                  No run output yet for this task. Use Run now to start a manual run; skipped
                  lines include a reason when the job exits early.
                </p>
              )}
              <div ref={logEndRef} />
            </div>
            <p className="scheduled-tasks-log-meta">
              {displayEvents.length || latestSeq
                ? `${displayEvents.length} lines${latestSeq ? ` · seq ${latestSeq}` : ""}`
                : optimisticStart || currentRun
                  ? "Starting…"
                  : "Waiting for events"}
              {selectedOutcome.summaryLine && !currentRun
                ? ` · ${selectedOutcome.summaryLine}`
                : ""}
              {selected?.quarantine?.last_error
                ? ` · last error: ${selected.quarantine.last_error}`
                : ""}
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
