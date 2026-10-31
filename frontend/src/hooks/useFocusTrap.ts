import { useEffect, useRef } from "react";
import {
  FOCUSABLE_SELECTOR,
  isDialogDismissKey,
  isFocusable,
  isTabKey,
  nextFocusTrapIndex,
} from "../lib/focusContract";

type UseFocusTrapOptions = {
  /** Whether the dialog/drawer is currently open. */
  open: boolean;
  /** Called to close — wired to Escape (unless `busy`). */
  onClose?: () => void;
  /** Suppress Escape-to-close while a destructive op is running (A11Y-009). */
  busy?: boolean;
  /** Skip the initial-focus-in step (rare — e.g. a toast-like overlay). */
  autoFocus?: boolean;
};

/**
 * A11Y-007 / A11Y-009 — the shared dialog/drawer focus contract:
 *  - Tab, on open, lands inside the container (first focusable element,
 *    or the container itself if nothing inside is focusable).
 *  - Tab/Shift+Tab cycle within the container (don't escape to the page).
 *  - Escape closes (unless `busy`), and focus returns to whatever was
 *    focused before the dialog opened.
 *
 * Returns a ref to attach to the dialog/drawer's outermost element.
 */
export function useFocusTrap<T extends HTMLElement = HTMLDivElement>({
  open,
  onClose,
  busy = false,
  autoFocus = true,
}: UseFocusTrapOptions) {
  const containerRef = useRef<T | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    previouslyFocused.current = (document.activeElement as HTMLElement) || null;

    const container = containerRef.current;
    if (autoFocus && container) {
      const first = container.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      (first && isFocusable(first) ? first : container).focus();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (isDialogDismissKey(event, { busy })) {
        event.stopPropagation();
        onClose?.();
        return;
      }
      if (!isTabKey(event) || !containerRef.current) return;
      const focusables = Array.from(
        containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter(isFocusable);
      if (focusables.length === 0) {
        event.preventDefault();
        return;
      }
      const currentIndex = focusables.indexOf(document.activeElement as HTMLElement);
      const nextIndex = nextFocusTrapIndex(focusables.length, currentIndex, {
        shiftKey: event.shiftKey,
      });
      event.preventDefault();
      focusables[nextIndex]?.focus();
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      // Restore focus to whatever opened the dialog/drawer.
      previouslyFocused.current?.focus?.();
    };
    // `busy`/`onClose`/`autoFocus` are read fresh each open via closure;
    // re-running this effect on every keystroke-adjacent change would steal
    // focus back to the first element, so only `open` retriggers it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return containerRef;
}
