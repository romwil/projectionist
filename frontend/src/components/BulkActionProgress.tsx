import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { bulkActionProgressView, shouldShowBulkActionProgress } from "../lib/bulkActionProgress.js";
import { createId } from "../lib/id.js";

type BulkProgressState = "running" | "success" | "error" | string;

type BulkProgress = {
  id: string;
  label: string;
  current: number;
  total: number;
  state: BulkProgressState;
};

type BulkStartOptions = {
  label?: string;
  total?: number;
  asynchronous?: boolean;
};

type BulkFinishOptions = {
  label?: string;
  state?: BulkProgressState;
};

type BulkActionProgressApi = {
  start: (opts: BulkStartOptions) => string | null;
  update: (id: string | null | undefined, current: number) => void;
  finish: (id: string | null | undefined, opts?: BulkFinishOptions) => void;
  clear: () => void;
};

const BulkActionProgressContext = createContext<BulkActionProgressApi | null>(null);

type BulkActionProgressProviderProps = {
  children?: React.ReactNode;
};

export function BulkActionProgressProvider({ children }: BulkActionProgressProviderProps) {
  const [progress, setProgress] = useState<BulkProgress | null>(null);
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => clearTimeout(clearTimerRef.current ?? undefined), []);

  const clear = useCallback(() => {
    clearTimeout(clearTimerRef.current ?? undefined);
    clearTimerRef.current = null;
    setProgress(null);
  }, []);

  const start = useCallback(({ label, total, asynchronous = false }: BulkStartOptions) => {
    if (!shouldShowBulkActionProgress({ total, asynchronous })) return null;
    clearTimeout(clearTimerRef.current ?? undefined);
    // createId works on HTTP LAN; crypto.randomUUID is missing/throws off HTTPS.
    const id = createId();
    setProgress({ id, label: label || "", current: 0, total: total ?? 0, state: "running" });
    return id;
  }, []);

  const update = useCallback((id: string | null | undefined, current: number) => {
    if (!id) return;
    setProgress((active) => (active?.id === id ? { ...active, current } : active));
  }, []);

  const finish = useCallback((id: string | null | undefined, { label, state = "success" }: BulkFinishOptions = {}) => {
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
    clearTimeout(clearTimerRef.current ?? undefined);
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

type BulkActionProgressProps = {
  progress?: BulkProgress | null;
  onDismiss?: (...args: any[]) => void;
};

export default function BulkActionProgress({ progress, onDismiss }: BulkActionProgressProps) {
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
