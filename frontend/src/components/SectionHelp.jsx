import { useEffect, useId, useRef } from "react";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover";

const HOVER_OPEN_DELAY_MS = 450;
const HOVER_CLOSE_DELAY_MS = 180;

/**
 * Compact section help: click the (?) icon or hover (with delay) for a short
 * plain-language popup. Escape and click-outside dismiss.
 */
export default function SectionHelp({
  label = "About this section",
  children,
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
        aria-label={label}
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
          aria-label={label}
          className="section-help-popover"
          data-testid={`${testId}-popover`}
          onMouseEnter={clearTimers}
          onMouseLeave={scheduleClose}
        >
          <div className="section-help-popover-body">{children}</div>
        </div>
      ) : null}
    </span>
  );
}

/** Alias for callers that prefer HelpPopover naming. */
export { SectionHelp as HelpPopover };
