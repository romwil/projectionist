import { useCallback, useEffect, useState } from "react";
import {
  listGroomingActions,
  refreshPurgeCandidates,
  undoGroomingAction,
} from "../api/client";
import {
  canUndoGroomingAction,
  formatGroomingActionLine,
  formatUndoSuccess,
  groomingActionStatusLabel,
} from "../lib/groomingActions.js";

/**
 * One-click grooming rerun + safe undo of the last destructive grooming run.
 *
 * "Rerun grooming" recomputes purge candidates (a non-destructive grooming pass).
 * Undo restores the CuratorX index rows a purge delete removed; it does not touch
 * Plex files (the delete never did) and embeddings backfill on the next enrichment.
 */
export default function GroomingUndoPanel({ onChanged }) {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [rerunning, setRerunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listGroomingActions({ limit: 10 });
      setActions(data?.actions || []);
      setError("");
    } catch (err) {
      setError(err.message || "Could not load grooming history.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUndo(action) {
    setBusyId(action.id);
    setNotice("");
    setError("");
    try {
      const result = await undoGroomingAction(action.id);
      setNotice(formatUndoSuccess(result));
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message || "Could not undo that grooming action.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRerun() {
    setRerunning(true);
    setNotice("");
    setError("");
    try {
      const payload = await refreshPurgeCandidates();
      const count = payload?.count ?? (payload?.items || []).length;
      setNotice(`Grooming rerun complete — ${count} purge candidate${count === 1 ? "" : "s"} recomputed.`);
      onChanged?.();
    } catch (err) {
      setError(err.message || "Could not rerun grooming.");
    } finally {
      setRerunning(false);
    }
  }

  return (
    <section className="grooming-panel" data-testid="grooming-panel">
      <div className="grooming-panel-head">
        <div>
          <p className="eyebrow">Grooming</p>
          <h3 className="dash-panel-title">Rerun &amp; safe undo</h3>
        </div>
        <button
          type="button"
          className="ghost"
          data-testid="grooming-rerun"
          disabled={rerunning}
          onClick={handleRerun}
        >
          {rerunning ? "Rerunning…" : "Rerun grooming"}
        </button>
      </div>

      <p className="scheduled-task-meta">
        Undo restores the CuratorX index rows a purge delete removed. Plex media files
        are never touched, and plot embeddings backfill on the next enrichment cycle.
      </p>

      {notice ? (
        <p className="status status-secondary" data-testid="grooming-notice">
          {notice}
        </p>
      ) : null}
      {error ? <p className="dash-panel-error">{error}</p> : null}

      {loading ? (
        <p className="status status-secondary">Loading grooming history…</p>
      ) : !actions.length ? (
        <p className="dash-empty" data-testid="grooming-empty">
          No reversible grooming runs yet. Deleting purge candidates records an undoable action here.
        </p>
      ) : (
        <ul className="grooming-action-list">
          {actions.map((action) => {
            const undoable = canUndoGroomingAction(action);
            return (
              <li
                key={action.id}
                className={`grooming-action-row ${action.undone_at != null ? "is-undone" : ""}`}
                data-testid={`grooming-action-${action.id}`}
              >
                <div>
                  <span className="grooming-action-summary">
                    {formatGroomingActionLine(action)}
                  </span>
                  <span className="grooming-action-status"> · {groomingActionStatusLabel(action)}</span>
                </div>
                {undoable ? (
                  <button
                    type="button"
                    className="ghost"
                    data-testid={`grooming-undo-${action.id}`}
                    disabled={busyId === action.id}
                    onClick={() => handleUndo(action)}
                  >
                    {busyId === action.id ? "Restoring…" : "Undo"}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
