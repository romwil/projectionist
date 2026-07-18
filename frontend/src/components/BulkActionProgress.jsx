import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { bulkActionProgressView, shouldShowBulkActionProgress } from "../lib/bulkActionProgress.js";

const BulkActionProgressContext = createContext(null);

export function BulkActionProgressProvider({ children }) {
  const [progress, setProgress] = useState(null);
  const clearTimerRef = useRef(null);

  useEffect(() => () => clearTimeout(clearTimerRef.current), []);

  const clear = useCallback(() => {
    clearTimeout(clearTimerRef.current);
    clearTimerRef.current = null;
    setProgress(null);
  }, []);

  const start = useCallback(({ label, total, asynchronous = false }) => {
    if (!shouldShowBulkActionProgress({ total, asynchronous })) return null;
    clearTimeout(clearTimerRef.current);
    const id = crypto.randomUUID();
    setProgress({ id, label, current: 0, total, state: "running" });
    return id;
  }, []);

  const update = useCallback((id, current) => {
    if (!id) return;
    setProgress((active) => (active?.id === id ? { ...active, current } : active));
  }, []);

  const finish = useCallback((id, { label, state = "success" } = {}) => {
    if (!id) return;
    setProgress((active) => {
      if (active?.id !== id) return active;
      return {
        ...active,
        label: label || active.label,
        current: active.total,
        state,
      };
    });
    clearTimeout(clearTimerRef.current);
    clearTimerRef.current = setTimeout(clear, state === "error" ? 5000 : 3000);
  }, [clear]);

  const value = useMemo(() => ({ start, update, finish, clear }), [clear, finish, start, update]);

  return (
    <BulkActionProgressContext.Provider value={value}>
      {children}
      <BulkActionProgress progress={progress} onDismiss={clear} />
    </BulkActionProgressContext.Provider>
  );
}

export function useBulkActionProgress() {
  const context = useContext(BulkActionProgressContext);
  if (!context) {
    throw new Error("useBulkActionProgress must be used inside BulkActionProgressProvider");
  }
  return context;
}

export default function BulkActionProgress({ progress, onDismiss }) {
  if (!progress) return null;
  const view = bulkActionProgressView(progress);
  const completed = progress.state !== "running";

  return (
    <aside
      className={`bulk-action-progress is-${progress.state}`}
      aria-live="polite"
      aria-atomic="true"
      data-testid="bulk-action-progress"
    >
      <div className="bulk-action-progress-copy">
        <p className="bulk-action-progress-label">{view.label}</p>
        {view.count ? <span className="bulk-action-progress-count">{view.count}</span> : null}
      </div>
      <div
        className="bulk-action-progress-bar"
        role="progressbar"
        aria-label={view.label}
        aria-valuenow={view.percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span className="bulk-action-progress-fill" style={{ width: `${view.percent}%` }} />
      </div>
      {completed ? (
        <button type="button" className="bulk-action-progress-dismiss" onClick={onDismiss} aria-label="Dismiss action status">
          ×
        </button>
      ) : null}
    </aside>
  );
}
