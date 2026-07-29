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
import SectionHelp from "./SectionHelp.jsx";

/**
 * Refresh purge-candidate cache + undo for index-only purge deletes.
 *
 * "Refresh purge candidates" recomputes the Storage Intelligence list (non-destructive).
 * Undo restores Projectionist index rows from **index-only** purge deletes.
 * Full purge (via *arr) deletes disk files and cannot be undone here.
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
      setError(err.message || "Could not load index undo history.");
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
      setError(err.message || "Could not undo that index-only delete.");
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
      setNotice(
        `Purge candidates refreshed — ${count} candidate${count === 1 ? "" : "s"} ready.`,
      );
      onChanged?.();
    } catch (err) {
      setError(err.message || "Could not refresh purge candidates.");
    } finally {
      setRerunning(false);
    }
  }

  return (
    <section className="grooming-panel" data-testid="grooming-panel">
      <div className="grooming-panel-head">
        <div className="grooming-panel-title-row">
          <div>
            <p className="eyebrow">Library maintenance</p>
            <h3 className="dash-panel-title">Purge candidates &amp; index undo</h3>
          </div>
          <SectionHelp
            label="About purge candidates and index undo"
            testId="grooming-section-help"
          >
            <p>
              <strong>Refresh purge candidates</strong> rebuilds the Storage Intelligence
              suggestions (stale or low-signal titles). It does not delete anything.
            </p>
            <p>
              <strong>Undo</strong> only restores Projectionist index rows from{" "}
              <em>index-only</em> deletes. Full remove deletes disk files through
              Radarr/Sonarr and cannot be undone here.
            </p>
          </SectionHelp>
        </div>
        <button
          type="button"
          className="ghost"
          data-testid="grooming-rerun"
          disabled={rerunning}
          onClick={handleRerun}
        >
          {rerunning ? "Refreshing…" : "Refresh purge candidates"}
        </button>
      </div>

      <p className="scheduled-task-meta">
        Undo restores Projectionist index rows from <strong>index-only</strong> purge deletes.
        Full remove deletes files via Radarr/Sonarr and cannot be undone. Embeddings backfill on
        the next enrichment cycle.
      </p>

      {notice ? (
        <p className="status status-secondary" data-testid="grooming-notice">
          {notice}
        </p>
      ) : null}
      {error ? <p className="dash-panel-error">{error}</p> : null}

      {loading ? (
        <p className="status status-secondary">Loading index undo history…</p>
      ) : !actions.length ? (
        <p className="dash-empty" data-testid="grooming-empty">
          No reversible index-only purge runs yet. Full removes are not undoable.
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
