import { createPortal } from "react-dom";
import SectionHelp from "./SectionHelp.jsx";
import {
  formatRemovalFreedLabel,
  hasRemovalSummary,
  normalizeRemovalSummary,
  removalPathsNote,
} from "../lib/bulkLibraryDelete.js";
import {
  REMOVAL_STOP_REMAINING_NOTE,
  isLiveRemoval,
  removalProgressView,
  removalStatusLabel,
} from "../lib/removalProgress.js";

function stopBubble(event) {
  event.stopPropagation();
}

function RemovalItem({ entry, showStatus }) {
  const status = entry.status || "removed";
  const pathNote = status === "removed" ? removalPathsNote(entry) : "";
  const files = Array.isArray(entry.files) ? entry.files : [];
  const folders = Array.isArray(entry.folders) ? entry.folders : [];
  return (
    <article
      className={`removal-summary-item is-${status}`}
      data-testid="removal-summary-item"
      data-status={status}
    >
      <header className="removal-summary-item-head">
        <h3>{entry.title || "Untitled"}</h3>
        <span className="removal-summary-item-bytes">
          {showStatus ? (
            <span className="removal-summary-status" data-testid="removal-item-status">
              {removalStatusLabel(status)}
            </span>
          ) : (
            formatRemovalFreedLabel(entry)
          )}
          {showStatus && status === "removed" ? (
            <span className="removal-summary-item-freed">{formatRemovalFreedLabel(entry)}</span>
          ) : null}
        </span>
      </header>
      {status === "failed" && entry.error ? (
        <p className="removal-summary-item-error" data-testid="removal-item-error">
          {entry.error}
        </p>
      ) : null}
      {status === "stopped" ? (
        <p className="status status-secondary" data-testid="removal-item-stopped">
          Left in the library. This title had not started.
        </p>
      ) : null}
      {status === "removed" && entry.note ? (
        <p className="status status-secondary" data-testid="removal-summary-paths-note">
          {entry.note}
        </p>
      ) : null}
      {status === "removed" && files.length ? (
        <div className="removal-summary-paths">
          <p className="removal-summary-paths-label">Files</p>
          <ul>
            {files.map((path) => (
              <li key={path} title={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : status === "removed" && !entry.note && pathNote ? (
        <p className="status status-secondary" data-testid="removal-summary-paths-note">
          {pathNote}
        </p>
      ) : null}
      {status === "removed" && folders.length ? (
        <div className="removal-summary-paths">
          <p className="removal-summary-paths-label">Folders</p>
          <ul>
            {folders.map((path) => (
              <li key={path} title={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

function RemovalSummaryPanel({
  result,
  onClose,
  onCancelRemaining,
  cancelRequested = false,
}) {
  const live = isLiveRemoval(result);
  const view = live ? removalProgressView(result) : null;
  const running = Boolean(view?.running);
  const summarySource = live ? result.result || result : result;
  const summary = normalizeRemovalSummary(running ? { results: [] } : summarySource);
  const { totals, results, errors, deleted } = summary;
  const titleCount = Number.isFinite(deleted) ? deleted : results.length;
  const hasSparsePaths = (live ? result.items : results).some(
    (entry) => entry.status !== "failed" && entry.status !== "stopped" && !((entry.files || []).length) && (entry.folders || []).length > 0,
  );
  const eyebrow = running
    ? "Removing"
    : hasSparsePaths || totals.bytes_source === "unknown"
      ? "Removal finished"
      : "Removal complete";
  const heading = view?.heading || "What was removed";
  const displayItems = live
    ? result.items
    : results.map((entry) => ({ ...entry, status: "removed" }));
  const showLiveStatus = Boolean(live);
  const indexOnly = (live ? result.mode : summarySource?.mode) === "index";

  function handleBackdrop() {
    if (running) return;
    onClose?.();
  }

  return (
    <div
      className="bulk-delete-modal-backdrop removal-summary-backdrop"
      data-testid="removal-summary-dialog"
      onMouseDown={stopBubble}
      onClick={handleBackdrop}
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
              <h2 id="removal-summary-title">{heading}</h2>
            </div>
            <SectionHelp
              label="About this removal summary"
              testId="removal-summary-help"
            >
              <p>
                Projectionist asked Radarr/Sonarr what files and folders belonged to
                each title before deleting them, then reports those paths and the
                storage freed. A title that is not in either app still deletes files
                whose path is already on the library row or reported by Plex, and
                those bytes stay in the totals. The “not in Sonarr” or “not in Radarr”
                line is only a note on that title. When no file path can be found,
                the note says so and the freed total stays 0 B. When *arr has a folder
                but no episode file list, the summary says the size is unknown instead
                of pretending 0 B was measured. Empty folders listed here are inferred
                from known paths — not from a full disk scan.
              </p>
            </SectionHelp>
          </div>
        </header>

        {indexOnly ? (
          <p className="status status-secondary" data-testid="removal-index-only-note">
            Index only. Disk files and Radarr/Sonarr were not changed.
          </p>
        ) : null}

        <div className="removal-summary-totals" data-testid="removal-summary-totals" aria-live="polite">
          <div>
            <strong data-testid={running ? "removal-progress-count" : undefined}>
              {running ? view.titleCountLabel : titleCount}
            </strong>
            <span>{running ? "titles" : `title${titleCount === 1 ? "" : "s"}`}</span>
          </div>
          <div>
            <strong>{running ? view.filesLabel : totals.files}</strong>
            <span>file{Number(running ? view.filesLabel : totals.files) === 1 ? "" : "s"}</span>
          </div>
          <div>
            <strong>{running ? view.foldersLabel : totals.folders}</strong>
            <span>folder{Number(running ? view.foldersLabel : totals.folders) === 1 ? "" : "s"}</span>
          </div>
          <div>
            <strong data-testid="removal-summary-freed">
              {running ? view.freedLabel : formatRemovalFreedLabel(totals)}
            </strong>
            <span>freed</span>
          </div>
        </div>

        <div className="removal-summary-scroll" data-testid="removal-summary-list">
          {displayItems.map((entry) => (
            <RemovalItem
              key={entry.rating_key || entry.title}
              entry={entry}
              showStatus={showLiveStatus}
            />
          ))}
        </div>

        {!live && errors.length ? (
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

        {result?.error && running === false ? (
          <p className="error" data-testid="removal-progress-error">
            {result.error}
          </p>
        ) : null}

        <div className="bulk-delete-modal-actions">
          {running ? (
            <>
              <p className="removal-progress-note">{REMOVAL_STOP_REMAINING_NOTE}</p>
              <button
                type="button"
                className="ghost removal-summary-stop"
                data-testid="removal-stop-remaining"
                disabled={cancelRequested}
                onClick={onCancelRemaining}
              >
                {cancelRequested ? "Stopping…" : "Stop remaining"}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="primary"
              data-testid="removal-summary-done"
              onClick={onClose}
            >
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Scrollable removal summary. While a delete is running this is the same
 * layout, filled in as each title finishes. Done closes the finished summary.
 */
export default function RemovalSummaryDialog({
  open,
  result = null,
  onClose,
  onCancelRemaining,
  cancelRequested = false,
}) {
  if (!open) return null;
  const live = isLiveRemoval(result);
  if (!live && !hasRemovalSummary(result)) return null;
  const panel = (
    <RemovalSummaryPanel
      result={result}
      onClose={onClose}
      onCancelRemaining={onCancelRemaining}
      cancelRequested={cancelRequested}
    />
  );
  if (typeof document === "undefined") return panel;
  return createPortal(panel, document.body);
}

export { RemovalSummaryPanel };
