import { useEffect, useState } from "react";
import {
  BULK_DELETE_CONFIRM_PHRASE,
  formatBulkDeletePreviewTitles,
  isBulkDeleteConfirmPhrase,
} from "../lib/bulkLibraryDelete.js";

/**
 * Hard-confirm dialog for removing CuratorX library index records by rating_key.
 * Does not delete Plex media files.
 */
export default function BulkLibraryDeleteDialog({
  open,
  titles = [],
  unavailableCount = 0,
  loading = false,
  error = "",
  onCancel,
  onConfirm,
}) {
  const [phrase, setPhrase] = useState("");

  useEffect(() => {
    if (!open) setPhrase("");
  }, [open]);

  if (!open) return null;

  const preview = formatBulkDeletePreviewTitles(titles, 5);
  const canConfirm = isBulkDeleteConfirmPhrase(phrase) && preview.total > 0 && !loading;

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
            <p className="eyebrow">Owner action</p>
            <h2 id="bulk-library-delete-title">Delete from CuratorX library</h2>
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

        <p className="bulk-delete-modal-warning">
          This removes {preview.total} title{preview.total === 1 ? "" : "s"} from the CuratorX
          library index. It does <strong>not</strong> delete files from Plex. Titles still in Plex
          can reappear on the next library sync.
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
            onClick={() => onConfirm?.()}
          >
            {loading ? "Deleting…" : `Delete ${preview.total || ""} from library`.trim()}
          </button>
        </div>
      </div>
    </div>
  );
}
