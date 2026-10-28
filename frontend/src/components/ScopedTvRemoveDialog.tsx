import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { DeleteConfirmPhrase, useDeleteConfirmationPref } from "./DeleteConfirmPhrase";
import {
  canConfirmLibraryRemoval,
  libraryRemovalNeedsTypedDelete,
} from "../lib/bulkLibraryDelete.js";

function stopBubble(event: React.MouseEvent) {
  event.stopPropagation();
}

type ScopedTvRemoveDialogProps = {
  open?: boolean;
  scope?: string;
  label?: string;
  loading?: boolean;
  error?: string;
  onCancel?: (...args: any[]) => void;
  onConfirm?: (...args: any[]) => void;
};

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
}: ScopedTvRemoveDialogProps) {
  const [phrase, setPhrase] = useState("");
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
  }, [open, label, scope]);

  if (!open || typeof document === "undefined") return null;

  const isSeason = String(scope) === "season";
  const needsTypedDelete = libraryRemovalNeedsTypedDelete(askDeleteConfirmation);
  const canConfirm = canConfirmLibraryRemoval({
    needsTypedDelete,
    phrase,
    hasTarget: Boolean(label),
    loading: loading || !prefReady || prefSaving,
  });

  async function handleConfirm() {
    const saved = await persistDontAskAgain();
    if (!saved) return;
    onConfirm?.();
  }

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

        {prefReady ? (
          <DeleteConfirmPhrase
            askDeleteConfirmation={askDeleteConfirmation}
            phrase={phrase}
            onPhraseChange={setPhrase}
            dontAskAgain={dontAskAgain}
            onDontAskAgainChange={setDontAskAgain}
            disabled={loading || prefSaving || !label}
            inputId="scoped-tv-remove-phrase"
            phraseTestId="scoped-tv-remove-phrase"
            dontAskTestId="scoped-tv-remove-dont-ask"
          />
        ) : (
          <p className="status status-secondary" data-testid="scoped-tv-remove-pref-loading">
            Checking confirmation…
          </p>
        )}

        {saveError || error ? (
          <p className="dash-panel-error" data-testid="scoped-tv-remove-error">
            {saveError || error}
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
            onClick={handleConfirm}
          >
            {loading ? "Removing…" : isSeason ? "Remove season" : "Remove episode"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
