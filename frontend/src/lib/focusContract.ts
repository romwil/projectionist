/**
 * A11Y-003 / A11Y-007 / A11Y-009 — shared focus-contract logic for dialogs,
 * drawers, and any other "overlay that traps focus" surface.
 *
 * Pure, DOM-shape-duck-typed functions so they're unit-testable without a
 * browser (see focusContract.test.mjs) — the real `useFocusTrap` hook
 * (src/hooks/useFocusTrap.ts) is the only piece that touches real DOM refs.
 */

/** Minimal shape these functions need from a "focusable element". */
export type FocusCandidate = {
  disabled?: boolean;
  tabIndex?: number;
  getAttribute?: (name: string) => string | null;
};

/** CSS selector used by `useFocusTrap` to query focusable descendants. */
export const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
  "[contenteditable='true']",
].join(",");

/** True when a candidate element should be reachable via Tab. */
export function isFocusable(el: FocusCandidate | null | undefined): boolean {
  if (!el) return false;
  if (el.disabled) return false;
  if (el.tabIndex != null && el.tabIndex < 0) return false;
  if (el.getAttribute?.("aria-hidden") === "true") return false;
  return true;
}

/**
 * Given the ordered list of focusable elements inside a trap and the
 * currently-focused index (-1 if focus is outside/unknown), compute the next
 * index Tab/Shift+Tab should land on, wrapping at both ends.
 */
export function nextFocusTrapIndex(
  count: number,
  currentIndex: number,
  { shiftKey = false }: { shiftKey?: boolean } = {},
): number {
  if (count <= 0) return -1;
  if (currentIndex < 0) return shiftKey ? count - 1 : 0;
  const next = shiftKey ? currentIndex - 1 : currentIndex + 1;
  if (next < 0) return count - 1;
  if (next >= count) return 0;
  return next;
}

/** True when this keydown should dismiss a dialog/drawer (Escape, unless a
 * destructive operation is in flight — A11Y-009 "unless destructive op
 * running"). */
export function isDialogDismissKey(
  event: { key?: string } | null | undefined,
  { busy = false }: { busy?: boolean } = {},
): boolean {
  if (!event || busy) return false;
  return event.key === "Escape";
}

/** True when a keydown is a Tab press that a focus trap should intercept. */
export function isTabKey(event: { key?: string } | null | undefined): boolean {
  return Boolean(event && event.key === "Tab");
}
