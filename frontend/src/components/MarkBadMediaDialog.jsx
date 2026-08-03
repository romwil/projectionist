import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

function stopBubble(event) {
  event.stopPropagation();
}

/**
 * Owner confirm: ask Radarr/Sonarr to delete bad file(s) and search for replacements.
 * Does not add import exclusions.
 */
export default function MarkBadMediaDialog({
  open,
  title = "",
  mediaType = "movie",
  loading = false,
  error = "",
  onCancel,
  onConfirm,
}) {
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAcknowledged(false);
  }, [open, title]);

  if (!open || typeof document === "undefined") return null;

  const label = String(title || "this title").trim() || "this title";
  const isShow = String(mediaType || "") === "show";
  const canConfirm = acknowledged && Boolean(label) && !loading;

  return createPortal(
    <div
      className="bulk-delete-modal-backdrop"
      data-testid="mark-bad-media-dialog"
      onMouseDown={stopBubble}
      onClick={onCancel}
    >
      <div
        className="bulk-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mark-bad-media-title"
        onMouseDown={stopBubble}
        onClick={stopBubble}
      >
        <header className="bulk-delete-modal-header">
          <div>
            <p className="eyebrow">Owner action</p>
            <h2 id="mark-bad-media-title">Mark as bad media</h2>
          </div>
          <button
            type="button"
            className="ghost"
            data-testid="mark-bad-media-cancel"
            disabled={loading}
            onClick={onCancel}
          >
            Cancel
          </button>
        </header>

        <p className="bulk-delete-modal-copy" data-testid="mark-bad-media-label">
          Ask {isShow ? "Sonarr" : "Radarr"} to replace the on-disk file for{" "}
          <strong>{label}</strong>.
        </p>
        <p className="bulk-delete-modal-copy">
          This removes the current bad file and starts a replacement search. It does{" "}
          <strong>not</strong> add an import exclusion — the title stays wanted and should
          re-download. Use <strong>Delete</strong> instead when you never want the title again.
        </p>

        <label className="bulk-delete-modal-mode">
          <input
            type="checkbox"
            checked={acknowledged}
            disabled={loading}
            data-testid="mark-bad-media-ack"
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          <span>
            <strong>Replace the bad file</strong>
            <span className="bulk-delete-modal-mode-hint">
              Sonarr/Radarr may delete the current file from disk and queue a new download.
            </span>
          </span>
        </label>

        {error ? (
          <p className="error" data-testid="mark-bad-media-error">
            {error}
          </p>
        ) : null}

        <div className="bulk-delete-modal-actions">
          <button
            type="button"
            className="btn-danger"
            data-testid="mark-bad-media-confirm"
            disabled={!canConfirm}
            onClick={() => onConfirm?.()}
          >
            {loading ? "Requesting replacement…" : "Mark as bad media"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
