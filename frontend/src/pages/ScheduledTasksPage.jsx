import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getScheduledTaskLog,
  listScheduledTasks,
  resetScheduledTaskQuarantine,
  runScheduledTask,
  updateScheduledTask,
} from "../api/client";
import {
  formatDurationMs,
  formatEpoch,
  formatInterval,
  formatLogLine,
  isTaskRunning,
  summarizeLastStatus,
  taskDisplayName,
  taskRowTone,
} from "../lib/scheduledTasks.js";

const POLL_IDLE_MS = 5000;
const POLL_ACTIVE_MS = 1200;

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
  const logEndRef = useRef(null);
  const latestSeqRef = useRef(0);

  const selected = useMemo(
    () => items.find((item) => item.name === selectedName) || null,
    [items, selectedName],
  );

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
    if (selectedName) {
      refreshLog({ reset: true });
    }
  }, [selectedName, refreshLog]);

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
  }, [events]);

  async function withBusy(name, fn) {
    setBusyNames((prev) => new Set(prev).add(name));
    setActionError("");
    try {
      await fn();
      await refreshList();
      await refreshLog({ reset: false });
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
    return withBusy(name, async () => {
      setSelectedName(name);
      await runScheduledTask(name);
      await refreshLog({ reset: true });
    });
  }

  function handleToggleEnabled(task) {
    return withBusy(task.name, async () => {
      await updateScheduledTask(task.name, { enabled: !task.enabled });
    });
  }

  function handleResetQuarantine(name) {
    return withBusy(name, async () => {
      await resetScheduledTaskQuarantine(name);
    });
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
        </div>
        <button type="button" className="ghost" onClick={() => refreshList()} data-testid="tasks-refresh">
          Refresh
        </button>
      </header>

      {error ? <p className="dash-panel-error" data-testid="tasks-error">{error}</p> : null}
      {actionError ? (
        <p className="dash-panel-error" data-testid="tasks-action-error">
          {actionError}
        </p>
      ) : null}

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
                        <td>
                          <div>{formatEpoch(task.last_finished_at ?? task.last_run_at)}</div>
                          {task.last_started_at ? (
                            <div className="scheduled-task-meta">
                              Started {formatEpoch(task.last_started_at)}
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
                    : lastRun
                      ? `Last ${summarizeLastStatus(lastRun.status)} · ${formatEpoch(lastRun.finished_at)}`
                      : "Select a task to monitor output"}
                </p>
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
            <div className="scheduled-tasks-log" data-testid="task-log">
              {events.length ? (
                events.map((event) => (
                  <div
                    key={event.seq}
                    className={`scheduled-tasks-log-line level-${event.level || "info"}`}
                    data-testid={`task-log-line-${event.seq}`}
                  >
                    {formatLogLine(event)}
                  </div>
                ))
              ) : (
                <p className="dash-empty">No run output yet for this task.</p>
              )}
              <div ref={logEndRef} />
            </div>
            <p className="scheduled-tasks-log-meta">
              {latestSeq ? `${events.length} lines · seq ${latestSeq}` : "Waiting for events"}
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
