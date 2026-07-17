/** Short-lived undo toast (e.g. after deleting a chat thread). */
export default function UndoToast({
  message,
  undoLabel = "Undo",
  onUndo,
  onDismiss,
}) {
  if (!message) return null;
  return (
    <div
      className="undo-toast"
      data-testid="undo-toast"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="undo-toast-message">{message}</span>
      <div className="undo-toast-actions">
        {onUndo ? (
          <button type="button" className="ghost" data-testid="undo-toast-undo" onClick={onUndo}>
            {undoLabel}
          </button>
        ) : null}
        {onDismiss ? (
          <button type="button" className="ghost" data-testid="undo-toast-dismiss" onClick={onDismiss}>
            Dismiss
          </button>
        ) : null}
      </div>
    </div>
  );
}
