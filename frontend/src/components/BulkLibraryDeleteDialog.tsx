import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { DeleteConfirmPhrase, useDeleteConfirmationPref } from "./DeleteConfirmPhrase";
import {
  LIBRARY_DELETE_MODE_FULL,
  LIBRARY_DELETE_MODE_INDEX,
  canConfirmLibraryRemoval,
  formatBulkDeletePreviewTitles,
  libraryDeleteModeLabel,
  libraryRemovalNeedsTypedDelete,
  normalizeLibraryDeleteMode,
} from "../lib/bulkLibraryDelete.js";

function stopBubble(event: any) {
  event.stopPropagation();
}

/**
 * Hard-confirm dialog for owner library delete.
 * Default mode removes Projectionist index rows only; full remove also
 * deletes via *arr (files + exclusion) and cleans Plex metadata.
 * Pass ``defaultMode`` / ``surface="purge"`` for Dashboard purge flows.
 *
 * Portaled to document.body so drawer scrims / click-outside handlers cannot
 * intercept mode radio clicks (drawer scrim is z-index 85; this dialog is 100).
 */
/** Props for BulkLibraryDeleteDialog. `any` = API/handler bags until Wave 4 client generics. */
type BulkLibraryDeleteDialogProps = {
  open?: boolean;
  titles?: any;
  unavailableCount?: number;
  loading?: boolean;
  error?: string;
  defaultMode?: any;
  surface?: any;
  onCancel?: (...args: any[]) => void;
  onConfirm?: (...args: any[]) => void;
};

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
}: BulkLibraryDeleteDialogProps) {
  const [phrase, setPhrase] = useState("");
  const [mode, setMode] = useState(() => normalizeLibraryDeleteMode(defaultMode));
  const isPurgeSurface = String(surface || "").trim().toLowerCase() === "purge";
  const {
    askDeleteConfirmation,
    prefReady,
    prefSaving,
    dontAskAgain,
    setDontAskAgain,
    saveError,
    persistDontAskAgain,
  } = useDeleteConfirmationPref(open);

  useEffect(() => {
    if (!open) return;
    setPhrase("");
    setMode(normalizeLibraryDeleteMode(defaultMode));
  }, [open, defaultMode]);

  if (!open || typeof document === "undefined") return null;

  const preview = formatBulkDeletePreviewTitles(titles, 5);
  const normalizedMode = normalizeLibraryDeleteMode(mode);
  const isFull = normalizedMode === LIBRARY_DELETE_MODE_FULL;
  const needsTypedDelete = libraryRemovalNeedsTypedDelete(askDeleteConfirmation);
  const canConfirm = canConfirmLibraryRemoval({
    needsTypedDelete,
    phrase,
    hasTarget: preview.total > 0,
    loading: loading || !prefReady || prefSaving,
  });
  const countLabel = preview.total === 1 ? "title" : "titles";

  function selectMode(nextMode: any, event: any) {
    stopBubble(event);
    setMode(nextMode);
  }

  async function handleConfirm() {
    const saved = await persistDontAskAgain();
    if (!saved) return;
    onConfirm?.({ mode: normalizedMode });
  }

  return createPortal(
    <div
      className="bulk-delete-modal-backdrop"
      data-testid="bulk-library-delete-dialog"
      onMouseDown={stopBubble}
      onClick={onCancel}
    >
      <div
        className="bulk-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bulk-library-delete-title"
        onMouseDown={stopBubble}
        onClick={stopBubble}
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
          <label className="bulk-delete-modal-mode" onClick={stopBubble} onMouseDown={stopBubble}>
            <input
              type="radio"
              name="bulk-library-delete-mode"
              value={LIBRARY_DELETE_MODE_INDEX}
              checked={normalizedMode === LIBRARY_DELETE_MODE_INDEX}
              disabled={loading}
              data-testid="bulk-library-delete-mode-index"
              onClick={stopBubble}
              onChange={(event) => selectMode(LIBRARY_DELETE_MODE_INDEX, event)}
            />
            <span>
              <strong>Index only</strong>
              <span className="bulk-delete-modal-mode-hint">
                {isPurgeSurface
                  ? "Remove from the Projectionist library index only. Undoable via Purge candidates & index undo. Does not delete Plex files or change Radarr/Sonarr."
                  : "Remove from the Projectionist library index. Does not delete Plex files or change Radarr/Sonarr."}
              </span>
            </span>
          </label>
          <label className="bulk-delete-modal-mode" onClick={stopBubble} onMouseDown={stopBubble}>
            <input
              type="radio"
              name="bulk-library-delete-mode"
              value={LIBRARY_DELETE_MODE_FULL}
              checked={normalizedMode === LIBRARY_DELETE_MODE_FULL}
              disabled={loading}
              data-testid="bulk-library-delete-mode-full"
              onClick={stopBubble}
              onChange={(event) => selectMode(LIBRARY_DELETE_MODE_FULL, event)}
            />
            <span>
              <strong>Full remove</strong>
              <span className="bulk-delete-modal-mode-hint">
                Delete media files via Radarr/Sonarr, add an import exclusion so lists cannot
                re-add the title, or delete from disk via Plex when the title is not in *arr.
                Then drop the Projectionist index row.
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
                Radarr/Sonarr (<code>deleteFiles</code> + import exclusion), or via Plex when
                the title is not in *arr, and drops the Projectionist index.{" "}
                <strong>Full purge is not undoable</strong> — index undo cannot restore files
                or index rows from a full remove. Titles not in *arr and not deletable via Plex
                stay in the index with a clear error.
              </>
            ) : (
              <>
                This permanently removes {preview.total} {countLabel} from your stack: disk files
                (through Radarr/Sonarr, or Plex when the title is not in *arr) and the Projectionist
                index. Titles not in *arr and not deletable via Plex stay in the index with a
                clear error.
              </>
            )
          ) : isPurgeSurface ? (
            <>
              This removes {preview.total} {countLabel} from the Projectionist library index only
              (undoable via Purge candidates &amp; index undo). It does <strong>not</strong> delete
              files from disk or Plex. Titles still in Plex can reappear on the next library sync.
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
            {unavailableCount > 0
              ? "None of the selected titles have a library rating key, so nothing can be deleted."
              : "No titles selected. Confirm stays disabled until at least one title is selected."}
          </p>
        )}

        {unavailableCount > 0 ? (
          <p className="status status-secondary" data-testid="bulk-library-delete-unavailable">
            {unavailableCount} selected title{unavailableCount === 1 ? "" : "s"} skipped (no
            rating key / not in library index).
          </p>
        ) : null}

        {prefReady ? (
          <DeleteConfirmPhrase
            askDeleteConfirmation={askDeleteConfirmation}
            phrase={phrase}
            onPhraseChange={setPhrase}
            dontAskAgain={dontAskAgain}
            onDontAskAgainChange={setDontAskAgain}
            disabled={loading || prefSaving || preview.total === 0}
            inputId="bulk-library-delete-phrase"
            phraseTestId="bulk-library-delete-phrase"
            dontAskTestId="bulk-library-delete-dont-ask"
          />
        ) : (
          <p className="status status-secondary" data-testid="bulk-library-delete-pref-loading">
            Checking confirmation…
          </p>
        )}

        {saveError || error ? (
          <p className="error" data-testid="bulk-library-delete-error">
            {saveError || error}
          </p>
        ) : null}

        <div className="bulk-delete-modal-actions">
          <button
            type="button"
            className="btn-danger"
            data-testid="bulk-library-delete-confirm"
            disabled={!canConfirm}
            onClick={handleConfirm}
          >
            {loading
              ? isFull
                ? "Fully removing…"
                : "Deleting…"
              : `${libraryDeleteModeLabel(normalizedMode)} ${preview.total || ""}`.trim()}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
