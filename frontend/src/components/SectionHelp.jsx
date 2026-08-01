import { useEffect, useId, useRef } from "react";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";
import { glossaryEntry, sectionHelpPlainBody } from "../lib/glossary.js";

const HOVER_OPEN_DELAY_MS = 450;
const HOVER_CLOSE_DELAY_MS = 180;

/**
 * Compact section help: click the (?) icon or hover (with delay) for a short
 * plain-language popup. Escape and click-outside dismiss.
 *
 * Pass `glossaryKey` (ops or craft term from the Live Admin glossary) to keep
 * Admin / HELP wording in sync without duplicating strings. Optional `children`
 * override the glossary blurb when you need richer markup.
 */
export default function SectionHelp({
  label = "About this section",
  glossaryKey = null,
  children = null,
  className = "",
  testId = "section-help",
}) {
  const panelId = useId();
  const hoverOpenTimer = useRef(null);
  const hoverCloseTimer = useRef(null);
  const { open, setOpen, rootRef, popoverRef } = useAnchoredPopover({
    closeOnOutside: true,
    closeOnEscape: true,
    outsideEvent: "mousedown",
  });

  const entry = glossaryKey ? glossaryEntry(glossaryKey) : null;
  const triggerLabel = entry?.label ? `About ${entry.label}` : label;
  const plainBody = children != null ? null : sectionHelpPlainBody(glossaryKey);
  const body =
    children != null ? (
      children
    ) : plainBody ? (
      <p>{plainBody}</p>
    ) : null;

  function clearTimers() {
    if (hoverOpenTimer.current) {
      window.clearTimeout(hoverOpenTimer.current);
      hoverOpenTimer.current = null;
    }
    if (hoverCloseTimer.current) {
      window.clearTimeout(hoverCloseTimer.current);
      hoverCloseTimer.current = null;
    }
  }

  useEffect(() => () => clearTimers(), []);

  function scheduleOpen() {
    clearTimers();
    hoverOpenTimer.current = window.setTimeout(() => setOpen(true), HOVER_OPEN_DELAY_MS);
  }

  function scheduleClose() {
    clearTimers();
    hoverCloseTimer.current = window.setTimeout(() => setOpen(false), HOVER_CLOSE_DELAY_MS);
  }

  function toggleClick(event) {
    event.preventDefault();
    event.stopPropagation();
    clearTimers();
    setOpen((value) => !value);
  }

  if (!body) return null;

  return (
    <span
      className={`section-help ${className}`.trim()}
      ref={rootRef}
      data-testid={testId}
      onMouseEnter={scheduleOpen}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        className="section-help-trigger"
        aria-label={triggerLabel}
        aria-expanded={open}
        aria-controls={panelId}
        data-testid={`${testId}-trigger`}
        onClick={toggleClick}
      >
        ?
      </button>
      {open ? (
        <div
          id={panelId}
          ref={popoverRef}
          role="dialog"
          aria-label={triggerLabel}
          className="section-help-popover"
          data-testid={`${testId}-popover`}
          onMouseEnter={clearTimers}
          onMouseLeave={scheduleClose}
        >
          <div className="section-help-popover-body">
            {entry?.label ? <p className="section-help-term">{entry.label}</p> : null}
            {body}
          </div>
        </div>
      ) : null}
    </span>
  );
}

/** Alias for callers that prefer HelpPopover naming. */
export { SectionHelp as HelpPopover };
