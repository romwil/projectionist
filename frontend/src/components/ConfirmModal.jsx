import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function stopBubble(event) {
  event.stopPropagation();
}

/**
 * In-app confirm — same overlay chrome as RecommendModal / WhatsNew
 * (dimmed stage, surface card, primary + ghost). No native dialog.
 */
export default function ConfirmModal({
  open,
  title = "Please confirm",
  body = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}) {
  const titleId = useId();
  const bodyId = useId();
  const dialogRef = useRef(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return undefined;
    const root = dialogRef.current;
    const previouslyFocused = document.activeElement;

    function focusables() {
      if (!root) return [];
      return [...root.querySelectorAll(FOCUSABLE)].filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );
    }

    const preferred = root?.querySelector(
      danger ? '[data-testid="confirm-modal-cancel"]' : '[data-testid="confirm-modal-confirm"]',
    );
    (preferred || focusables()[0])?.focus();

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCancelRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !root) return;
      const list = focusables();
      if (!list.length) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, [open, danger]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="recommend-modal-backdrop"
      data-testid="confirm-modal"
      onClick={onCancel}
    >
      <div
        ref={dialogRef}
        className="recommend-modal confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={body ? bodyId : undefined}
        onClick={stopBubble}
      >
        <header className="recommend-modal-header">
          <div>
            <h2 id={titleId}>{title}</h2>
          </div>
        </header>
        {body ? (
          <p className="confirm-modal-copy" id={bodyId}>
            {body}
          </p>
        ) : null}
        <div className="recommend-modal-actions">
          <button
            type="button"
            className="ghost"
            data-testid="confirm-modal-cancel"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "primary danger" : "primary"}
            data-testid="confirm-modal-confirm"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
