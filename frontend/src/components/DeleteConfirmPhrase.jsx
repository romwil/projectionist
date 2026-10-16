import { useEffect, useState } from "react";
import { getAskDeleteConfirmation, saveAskDeleteConfirmation } from "../api/client";
import {
  BULK_DELETE_CONFIRM_PHRASE,
  libraryRemovalNeedsTypedDelete,
} from "../lib/bulkLibraryDelete.js";

/**
 * Loads the owner preference for typed DELETE. Fail closed: a failed fetch
 * still asks for the word.
 */
export function useDeleteConfirmationPref(open) {
  const [ask, setAsk] = useState(true);
  const [ready, setReady] = useState(false);
  const [dontAskAgain, setDontAskAgain] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setDontAskAgain(false);
    setSaveError("");
    setReady(false);
    setAsk(true);
    getAskDeleteConfirmation()
      .then((data) => {
        if (!cancelled) setAsk(data?.ask_delete_confirmation !== false);
      })
      .catch(() => {
        if (!cancelled) setAsk(true);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function persistDontAskAgain() {
    if (!dontAskAgain || !libraryRemovalNeedsTypedDelete(ask)) return true;
    setSaving(true);
    setSaveError("");
    try {
      const saved = await saveAskDeleteConfirmation(false);
      const next = saved?.ask_delete_confirmation !== false;
      setAsk(next);
      if (next) {
        setSaveError("Could not turn off the DELETE confirmation.");
        return false;
      }
      setDontAskAgain(false);
      return true;
    } catch (error) {
      setSaveError(error?.message || "Could not turn off the DELETE confirmation.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  return {
    askDeleteConfirmation: ask,
    prefReady: ready,
    prefSaving: saving,
    dontAskAgain,
    setDontAskAgain,
    saveError,
    persistDontAskAgain,
  };
}

export function DeleteConfirmPhrase({
  askDeleteConfirmation,
  phrase,
  onPhraseChange,
  dontAskAgain,
  onDontAskAgainChange,
  disabled,
  inputId,
  phraseTestId,
  dontAskTestId,
}) {
  if (!libraryRemovalNeedsTypedDelete(askDeleteConfirmation)) return null;
  return (
    <>
      <label className="bulk-delete-modal-confirm-label" htmlFor={inputId}>
        Type <kbd>{BULK_DELETE_CONFIRM_PHRASE}</kbd> to confirm
        <input
          id={inputId}
          className="bulk-delete-modal-confirm-input"
          data-testid={phraseTestId}
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={phrase}
          disabled={disabled}
          onChange={(event) => onPhraseChange(event.target.value)}
        />
      </label>
      <label className="bulk-delete-dont-ask" data-testid={dontAskTestId}>
        <input
          type="checkbox"
          checked={Boolean(dontAskAgain)}
          disabled={disabled}
          onChange={(event) => onDontAskAgainChange(event.target.checked)}
        />
        <span>Don&apos;t ask again</span>
      </label>
    </>
  );
}
