import type { MouseEvent } from "react";
import { findMainLandmark } from "../lib/skipLink";

/**
 * A11Y-008: the first focusable element on every route. Moves focus into
 * the page's main landmark without touching the router's location.
 */
export default function SkipLink() {
  function onActivate(event: MouseEvent<HTMLAnchorElement>) {
    const target = findMainLandmark(document);
    if (!target) return;
    event.preventDefault();
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.focus();
    target.scrollIntoView?.({ block: "start" });
  }

  return (
    <a className="skip-link" href="#main" onClick={onActivate} data-testid="skip-link">
      Skip to content
    </a>
  );
}
