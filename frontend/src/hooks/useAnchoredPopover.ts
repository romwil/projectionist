import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";

/**
 * Shared popover/menu behavior: open state, dismiss-on-outside-click and/or
 * Escape, and optional portal placement (getBoundingClientRect against an anchor,
 * re-run on resize/scroll). Extracted from the previously-duplicated logic in
 * ShareActionMenu, PosterActionMenu, PersonaSelector, UserMenu, and AppNav.
 *
 * The hook is intentionally configurable so each adopter keeps its EXACT prior
 * behavior — placement math, which events dismiss it, and whether it owns its
 * open state or is controlled by a parent.
 *
 * @param {Object} [options]
 * @param {boolean} [options.open] Controlled open state. When provided the hook
 *   does not own the state; dismissals call `onOpenChange(false)`.
 * @param {(next: boolean) => void} [options.onOpenChange] Called with the next
 *   open value whenever the hook requests a change (controlled or uncontrolled).
 * @param {boolean} [options.initialOpen=false] Initial open for uncontrolled use.
 * @param {boolean} [options.closeOnOutside=true] Dismiss when a pointer event
 *   lands outside both the root and popover refs.
 * @param {string} [options.outsideEvent="mousedown"] Event used for outside dismiss.
 * @param {boolean} [options.closeOnEscape=false] Dismiss on the Escape key.
 * @param {string} [options.anchorSelector] Selector queried inside `rootRef` for
 *   the placement anchor; falls back to `rootRef` itself.
 * @param {(anchor: DOMRect, popover: DOMRect) => Object} [options.placement]
 *   Returns the popover style object. Omit for menus that don't portal/position.
 * @param {string|number} [options.repositionKey] Extra dependency: when it
 *   changes while open, placement recomputes (e.g. status text / submenu state
 *   that resizes the popover).
 */
type AnchoredPopoverOptions = {
  open?: boolean;
  onOpenChange?: (next: boolean) => void;
  initialOpen?: boolean;
  closeOnOutside?: boolean;
  outsideEvent?: string;
  closeOnEscape?: boolean;
  anchorSelector?: string;
  placement?: (anchor: DOMRect, popover: DOMRect) => CSSProperties;
  repositionKey?: string | number;
};

export function useAnchoredPopover({
  open: controlledOpen,
  onOpenChange,
  initialOpen = false,
  closeOnOutside = true,
  outsideEvent = "mousedown",
  closeOnEscape = false,
  anchorSelector,
  placement,
  repositionKey,
}: AnchoredPopoverOptions = {}) {
  const controlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(initialOpen);
  const open = controlled ? Boolean(controlledOpen) : internalOpen;

  const rootRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties | null>(null);

  const setOpen = useCallback(
    (value: boolean | ((current: boolean) => boolean)) => {
      const next = typeof value === "function" ? value(open) : value;
      if (!controlled) setInternalOpen(next);
      onOpenChange?.(next);
    },
    [open, controlled, onOpenChange],
  );

  const close = useCallback(() => setOpen(false), [setOpen]);

  useEffect(() => {
    if (!open) return undefined;
    const handleOutside = (event: Event) => {
      const target = event.target;
      if (target instanceof Node && rootRef.current?.contains(target)) return;
      if (target instanceof Node && popoverRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    if (closeOnOutside) document.addEventListener(outsideEvent, handleOutside);
    if (closeOnEscape) document.addEventListener("keydown", handleKey);
    return () => {
      if (closeOnOutside) document.removeEventListener(outsideEvent, handleOutside);
      if (closeOnEscape) document.removeEventListener("keydown", handleKey);
    };
  }, [open, closeOnOutside, outsideEvent, closeOnEscape, setOpen]);

  useLayoutEffect(() => {
    if (!open || !placement) return undefined;
    const position = () => {
      const anchorEl = anchorSelector ? rootRef.current?.querySelector(anchorSelector) : rootRef.current;
      const anchor = anchorEl?.getBoundingClientRect();
      const menu = popoverRef.current?.getBoundingClientRect();
      if (!anchor || !menu) return;
      setPopoverStyle(placement(anchor, menu));
    };
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
    // `repositionKey` is an intentional trigger to recompute placement when the
    // popover's contents resize (e.g. status text / submenu open).
  }, [open, placement, anchorSelector, repositionKey]);

  return { open, setOpen, close, rootRef, popoverRef, popoverStyle };
}
