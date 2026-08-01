import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  BULK_DELETE_CONFIRM_PHRASE,
  isBulkDeleteConfirmPhrase,
} from "../lib/bulkLibraryDelete.js";

function stopBubble(event) {
  event.stopPropagation();
}

/**
 * Typed-DELETE confirm for owner season / episode remove (full disk via Sonarr).
 */
export default function ScopedTvRemoveDialog({
  open,
  scope = "episode",
  label = "",
  loading = false,
  error = "",
  onCancel,
  onConfirm,
}) {
  const [phrase, setPhrase] = useState("");

  useEffect(() => {
    if (!open) return;
    setPhrase("");
  }, [open, label, scope]);

  if (!open || typeof document === "undefined") return null;

  const isSeason = String(scope) === "season";
  const canConfirm = isBulkDeleteConfirmPhrase(phrase) && Boolean(label) && !loading;

  return createPortal(
    <div
      className="bulk-delete-modal-backdrop"
      data-testid="scoped-tv-remove-dialog"
      onMouseDown={stopBubble}
      onClick={onCancel}
    >
      <div
        className="bulk-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="scoped-tv-remove-title"
        onMouseDown={stopBubble}
        onClick={stopBubble}
      >
        <header className="bulk-delete-modal-header">
          <div>
            <p className="eyebrow">Owner action</p>
            <h2 id="scoped-tv-remove-title">
              {isSeason ? "Remove season from disk" : "Remove episode from disk"}
            </h2>
          </div>
        </header>

        <p className="bulk-delete-modal-copy">
          This deletes media files through Sonarr, removes the Plex library entry, and
          drops the episode{isSeason ? "s" : ""} from Projectionist&apos;s index. It
          cannot be undone here.
        </p>
        <p className="bulk-delete-modal-copy" data-testid="scoped-tv-remove-label">
          <strong>{label || "Untitled"}</strong>
        </p>

        <label className="bulk-delete-confirm-label" htmlFor="scoped-tv-remove-phrase">
          Type <kbd>{BULK_DELETE_CONFIRM_PHRASE}</kbd> to confirm
        </label>
        <input
          id="scoped-tv-remove-phrase"
          className="bulk-delete-confirm-input"
          data-testid="scoped-tv-remove-phrase"
          autoComplete="off"
          spellCheck={false}
          value={phrase}
          disabled={loading}
          onChange={(event) => setPhrase(event.target.value)}
        />

        {error ? (
          <p className="dash-panel-error" data-testid="scoped-tv-remove-error">
            {error}
          </p>
        ) : null}

        <div className="bulk-delete-modal-actions">
          <button
            type="button"
            className="ghost"
            data-testid="scoped-tv-remove-cancel"
            disabled={loading}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="primary danger"
            data-testid="scoped-tv-remove-confirm"
            disabled={!canConfirm}
            onClick={() => onConfirm?.()}
          >
            {loading ? "Removing…" : isSeason ? "Remove season" : "Remove episode"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
