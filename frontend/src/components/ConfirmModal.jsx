import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function stopBubble(event) {
  event.stopPropagation();
}

function normalizePrompt(prompt) {
  if (!prompt) return null;
  if (prompt === true) return { label: "", placeholder: "", type: "text" };
  return {
    label: prompt.label || "",
    placeholder: prompt.placeholder || "",
    type: prompt.type || "text",
    defaultValue: prompt.defaultValue || "",
  };
}

/**
 * In-app confirm — same overlay chrome as RecommendModal / WhatsNew
 * (dimmed stage, surface card, primary + ghost). No native dialog.
 * Optional `prompt` is an in-app field (replaces window.prompt).
 */
export default function ConfirmModal({
  open,
  title = "Please confirm",
  body = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  prompt = null,
  onConfirm,
  onCancel,
}) {
  const titleId = useId();
  const bodyId = useId();
  const promptId = useId();
  const dialogRef = useRef(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;
  const promptSpec = normalizePrompt(prompt);
  const hasPrompt = Boolean(promptSpec);
  const [promptValue, setPromptValue] = useState("");
  const promptReady = !hasPrompt || Boolean(promptValue.trim());

  useEffect(() => {
    if (!open) {
      setPromptValue("");
      return undefined;
    }
    setPromptValue(promptSpec?.defaultValue || "");
    return undefined;
  }, [open, promptSpec?.defaultValue]);

  function handleConfirm() {
    if (!promptReady) return;
    if (hasPrompt) onConfirm?.(promptValue.trim());
    else onConfirm?.();
  }

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
      hasPrompt
        ? '[data-testid="confirm-modal-prompt"]'
        : danger
          ? '[data-testid="confirm-modal-cancel"]'
          : '[data-testid="confirm-modal-confirm"]',
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
  }, [open, danger, hasPrompt]);

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
        {promptSpec ? (
          <label className="confirm-modal-field" htmlFor={promptId}>
            {promptSpec.label ? <span>{promptSpec.label}</span> : null}
            <input
              id={promptId}
              type={promptSpec.type === "password" ? "password" : "text"}
              value={promptValue}
              placeholder={promptSpec.placeholder}
              autoComplete="off"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              data-testid="confirm-modal-prompt"
              onChange={(event) => setPromptValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleConfirm();
                }
              }}
            />
          </label>
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
            disabled={!promptReady}
            onClick={handleConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
