import { useEffect, useState } from "react";
import {
  BULK_DELETE_CONFIRM_PHRASE,
  LIBRARY_DELETE_MODE_FULL,
  LIBRARY_DELETE_MODE_INDEX,
  formatBulkDeletePreviewTitles,
  isBulkDeleteConfirmPhrase,
  libraryDeleteModeLabel,
  normalizeLibraryDeleteMode,
} from "../lib/bulkLibraryDelete.js";

/**
 * Hard-confirm dialog for owner library delete.
 * Default mode removes Projectionist index rows only; full remove also
 * deletes via *arr (files + exclusion) and cleans Plex metadata.
 * Pass ``defaultMode`` / ``surface="purge"`` for Dashboard purge flows.
 */
export default function BulkLibraryDeleteDialog({
  open,
  titles = [],
  unavailableCount = 0,
  loading = false,
  error = "",
  defaultMode = LIBRARY_DELETE_MODE_INDEX,
  surface = "",
  onCancel,
  onConfirm,
}) {
  const [phrase, setPhrase] = useState("");
  const [mode, setMode] = useState(() => normalizeLibraryDeleteMode(defaultMode));
  const isPurgeSurface = String(surface || "").trim().toLowerCase() === "purge";

  useEffect(() => {
    setPhrase("");
    setMode(normalizeLibraryDeleteMode(defaultMode));
  }, [open, defaultMode]);

  if (!open) return null;

  const preview = formatBulkDeletePreviewTitles(titles, 5);
  const normalizedMode = normalizeLibraryDeleteMode(mode);
  const isFull = normalizedMode === LIBRARY_DELETE_MODE_FULL;
  const canConfirm = isBulkDeleteConfirmPhrase(phrase) && preview.total > 0 && !loading;
  const countLabel = preview.total === 1 ? "title" : "titles";

  return (
    <div
      className="bulk-delete-modal-backdrop"
      data-testid="bulk-library-delete-dialog"
      onClick={onCancel}
    >
      <div
        className="bulk-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bulk-library-delete-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="bulk-delete-modal-header">
          <div>
            <p className="eyebrow">{isPurgeSurface ? "Storage Intelligence" : "Owner action"}</p>
            <h2 id="bulk-library-delete-title">
              {isFull
                ? isPurgeSurface
                  ? "Fully purge from library stack"
                  : "Fully remove from library stack"
                : isPurgeSurface
                  ? "Prune purge candidates (index only)"
                  : "Delete from Projectionist library"}
            </h2>
          </div>
          <button
            type="button"
            className="ghost"
            data-testid="bulk-library-delete-cancel"
            disabled={loading}
            onClick={onCancel}
          >
            Cancel
          </button>
        </header>

        <fieldset className="bulk-delete-modal-modes" data-testid="bulk-library-delete-modes">
          <legend className="bulk-delete-modal-modes-legend">Removal scope</legend>
          <label className="bulk-delete-modal-mode">
            <input
              type="radio"
              name="bulk-library-delete-mode"
              value={LIBRARY_DELETE_MODE_INDEX}
              checked={normalizedMode === LIBRARY_DELETE_MODE_INDEX}
              disabled={loading}
              data-testid="bulk-library-delete-mode-index"
              onChange={() => setMode(LIBRARY_DELETE_MODE_INDEX)}
            />
            <span>
              <strong>Index only</strong>
              <span className="bulk-delete-modal-mode-hint">
                {isPurgeSurface
                  ? "Remove from the Projectionist library index only. Undoable via Grooming. Does not delete Plex files or change Radarr/Sonarr."
                  : "Remove from the Projectionist library index. Does not delete Plex files or change Radarr/Sonarr."}
              </span>
            </span>
          </label>
          <label className="bulk-delete-modal-mode">
            <input
              type="radio"
              name="bulk-library-delete-mode"
              value={LIBRARY_DELETE_MODE_FULL}
              checked={normalizedMode === LIBRARY_DELETE_MODE_FULL}
              disabled={loading}
              data-testid="bulk-library-delete-mode-full"
              onChange={() => setMode(LIBRARY_DELETE_MODE_FULL)}
            />
            <span>
              <strong>Full remove</strong>
              <span className="bulk-delete-modal-mode-hint">
                Delete media files via Radarr/Sonarr, add an import exclusion so lists cannot
                re-add the title, remove it from Plex when configured, then drop the Projectionist
                index row.
              </span>
            </span>
          </label>
        </fieldset>

        <p
          className={`bulk-delete-modal-warning${isFull ? " bulk-delete-modal-warning-danger" : ""}`}
          data-testid="bulk-library-delete-warning"
        >
          {isFull ? (
            isPurgeSurface ? (
              <>
                This permanently deletes disk files for {preview.total} {countLabel} via
                Radarr/Sonarr (<code>deleteFiles</code> + import exclusion), removes the Plex
                library entry when configured, and drops the Projectionist index.{" "}
                <strong>Full purge is not undoable</strong> — Grooming undo cannot restore files
                or index rows from a full remove. Titles not managed by *arr stay in the index with
                a clear error.
              </>
            ) : (
              <>
                This permanently removes {preview.total} {countLabel} from your stack: disk files
                (through Radarr/Sonarr), Plex library entry, and the Projectionist index. Titles not
                managed by *arr cannot be fully removed — those stay in the index with a clear error.
              </>
            )
          ) : isPurgeSurface ? (
            <>
              This removes {preview.total} {countLabel} from the Projectionist library index only
              (undoable via Grooming). It does <strong>not</strong> delete files from disk or Plex.
              Titles still in Plex can reappear on the next library sync.
            </>
          ) : (
            <>
              This removes {preview.total} {countLabel} from the Projectionist library index. It does{" "}
              <strong>not</strong> delete files from Plex. Titles still in Plex can reappear on the
              next library sync.
            </>
          )}
        </p>

        {preview.shown.length ? (
          <ul className="bulk-delete-modal-titles" data-testid="bulk-library-delete-titles">
            {preview.shown.map((title) => (
              <li key={title}>{title}</li>
            ))}
            {preview.remaining > 0 ? (
              <li className="bulk-delete-modal-more">…and {preview.remaining} more</li>
            ) : null}
          </ul>
        ) : (
          <p className="error" data-testid="bulk-library-delete-none">
            None of the selected titles have a library rating key, so nothing can be deleted.
          </p>
        )}

        {unavailableCount > 0 ? (
          <p className="status status-secondary" data-testid="bulk-library-delete-unavailable">
            {unavailableCount} selected title{unavailableCount === 1 ? "" : "s"} skipped (no
            rating key / not in library index).
          </p>
        ) : null}

        <label className="bulk-delete-modal-confirm-label" htmlFor="bulk-library-delete-phrase">
          Type <kbd>{BULK_DELETE_CONFIRM_PHRASE}</kbd> to confirm
          <input
            id="bulk-library-delete-phrase"
            className="bulk-delete-modal-confirm-input"
            data-testid="bulk-library-delete-phrase"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={phrase}
            disabled={loading || preview.total === 0}
            onChange={(event) => setPhrase(event.target.value)}
          />
        </label>

        {error ? (
          <p className="error" data-testid="bulk-library-delete-error">
            {error}
          </p>
        ) : null}

        <div className="bulk-delete-modal-actions">
          <button
            type="button"
            className="btn-danger"
            data-testid="bulk-library-delete-confirm"
            disabled={!canConfirm}
            onClick={() => onConfirm?.({ mode: normalizedMode })}
          >
            {loading
              ? isFull
                ? "Fully removing…"
                : "Deleting…"
              : `${libraryDeleteModeLabel(normalizedMode)} ${preview.total || ""}`.trim()}
          </button>
        </div>
      </div>
    </div>
  );
}
