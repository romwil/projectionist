import { createPortal } from "react-dom";
import SectionHelp from "./SectionHelp.jsx";
import {
  formatRemovalFreedLabel,
  hasRemovalSummary,
  normalizeRemovalSummary,
  removalPathsNote,
} from "../lib/bulkLibraryDelete.js";

function stopBubble(event) {
  event.stopPropagation();
}

/**
 * Scrollable post-delete results for full remove (bulk or single).
 * Portaled above drawer scrims — same stacking as BulkLibraryDeleteDialog.
 */
export default function RemovalSummaryDialog({ open, result = null, onClose }) {
  if (!open || typeof document === "undefined") return null;
  if (!hasRemovalSummary(result)) return null;

  const summary = normalizeRemovalSummary(result);
  const { totals, results, errors, deleted } = summary;
  const titleCount = Number.isFinite(deleted) ? deleted : results.length;
  const hasSparsePaths = results.some(
    (entry) => !entry.files.length && entry.folders.length > 0,
  );
  const eyebrow = hasSparsePaths || totals.bytes_source === "unknown"
    ? "Removal finished"
    : "Removal complete";

  return createPortal(
    <div
      className="bulk-delete-modal-backdrop removal-summary-backdrop"
      data-testid="removal-summary-dialog"
      onMouseDown={stopBubble}
      onClick={onClose}
    >
      <div
        className="bulk-delete-modal removal-summary-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="removal-summary-title"
        onMouseDown={stopBubble}
        onClick={stopBubble}
      >
        <header className="bulk-delete-modal-header">
          <div className="removal-summary-title-row">
            <div>
              <p className="eyebrow">{eyebrow}</p>
              <h2 id="removal-summary-title">What was removed</h2>
            </div>
            <SectionHelp
              label="About this removal summary"
              testId="removal-summary-help"
            >
              <p>
                Projectionist asked Radarr/Sonarr what files and folders belonged to
                each title before deleting them, then reports those paths and the
                storage freed. When *arr has a folder but no episode file list, the
                summary says so instead of pretending 0 B was measured. Empty folders
                listed here are inferred from known paths — not from a full disk scan.
              </p>
            </SectionHelp>
          </div>
          <button
            type="button"
            className="ghost"
            data-testid="removal-summary-close"
            onClick={onClose}
          >
            Close
          </button>
        </header>

        <div className="removal-summary-totals" data-testid="removal-summary-totals">
          <div>
            <strong>{titleCount}</strong>
            <span>title{titleCount === 1 ? "" : "s"}</span>
          </div>
          <div>
            <strong>{totals.files}</strong>
            <span>file{totals.files === 1 ? "" : "s"}</span>
          </div>
          <div>
            <strong>{totals.folders}</strong>
            <span>folder{totals.folders === 1 ? "" : "s"}</span>
          </div>
          <div>
            <strong data-testid="removal-summary-freed">
              {formatRemovalFreedLabel(totals)}
            </strong>
            <span>freed</span>
          </div>
        </div>

        <div className="removal-summary-scroll" data-testid="removal-summary-list">
          {results.map((entry) => {
            const pathNote = removalPathsNote(entry);
            return (
              <article
                key={entry.rating_key || entry.title}
                className="removal-summary-item"
                data-testid="removal-summary-item"
              >
                <header className="removal-summary-item-head">
                  <h3>{entry.title || "Untitled"}</h3>
                  <span className="removal-summary-item-bytes">
                    {formatRemovalFreedLabel(entry)}
                  </span>
                </header>
                {entry.files.length ? (
                  <div className="removal-summary-paths">
                    <p className="removal-summary-paths-label">Files</p>
                    <ul>
                      {entry.files.map((path) => (
                        <li key={path} title={path}>
                          <code>{path}</code>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : pathNote ? (
                  <p
                    className="status status-secondary"
                    data-testid="removal-summary-paths-note"
                  >
                    {pathNote}
                  </p>
                ) : null}
                {entry.folders.length ? (
                  <div className="removal-summary-paths">
                    <p className="removal-summary-paths-label">Folders</p>
                    <ul>
                      {entry.folders.map((path) => (
                        <li key={path} title={path}>
                          <code>{path}</code>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>

        {errors.length ? (
          <div className="removal-summary-errors" data-testid="removal-summary-errors">
            <p className="removal-summary-paths-label">Could not fully remove</p>
            <ul>
              {errors.map((err) => (
                <li key={`${err.rating_key || ""}-${err.title || ""}`}>
                  <strong>{err.title || err.rating_key || "Title"}</strong>
                  {err.error ? ` — ${err.error}` : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="bulk-delete-modal-actions">
          <button
            type="button"
            className="primary"
            data-testid="removal-summary-done"
            onClick={onClose}
          >
            Done
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
