import { useEffect, useMemo, useRef } from "react";

function kindIcon(kind) {
  switch (kind) {
    case "tool_start":
      return "build";
    case "tool_result":
      return "check_circle";
    case "token_note":
      return "edit_note";
    default:
      return "psychology";
  }
}

export default function TypingIndicator({
  label = "Curator is thinking",
  activityLog = [],
  expanded = false,
  onToggle,
  interactive = false,
  streaming = true,
}) {
  const displayLabel = useMemo(() => label, [label]);
  const panelRef = useRef(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    if (!expanded) return undefined;
    const panel = panelRef.current;
    if (!panel) return undefined;

    const onScroll = () => {
      const distance = panel.scrollHeight - panel.scrollTop - panel.clientHeight;
      stickToBottomRef.current = distance < 28;
    };
    panel.addEventListener("scroll", onScroll, { passive: true });
    return () => panel.removeEventListener("scroll", onScroll);
  }, [expanded]);

  useEffect(() => {
    if (!expanded || !stickToBottomRef.current) return;
    const panel = panelRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [activityLog, expanded]);

  const toggle = () => {
    if (!interactive || !onToggle) return;
    onToggle();
  };

  const onKeyDown = (event) => {
    if (!interactive) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggle?.();
    }
  };

  return (
    <div
      className={`typing-indicator-wrap${expanded ? " is-expanded" : ""}${interactive ? " is-interactive" : ""}${streaming ? " is-streaming" : ""}`}
      data-testid="typing-indicator-wrap"
    >
      <div
        className="typing-indicator"
        role={interactive ? "button" : undefined}
        tabIndex={interactive ? 0 : undefined}
        aria-expanded={interactive ? expanded : undefined}
        aria-controls={interactive ? "agent-activity-panel" : undefined}
        aria-live="polite"
        data-testid="typing-indicator"
        onClick={toggle}
        onKeyDown={onKeyDown}
        title={interactive ? (expanded ? "Hide agent activity" : "Show agent activity") : undefined}
      >
        <span className="typing-indicator-label">{displayLabel}</span>
        {streaming ? (
          <span className="typing-indicator-dots" aria-hidden="true">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </span>
        ) : null}
        {interactive ? (
          <span className="material-symbols-outlined typing-indicator-chevron" aria-hidden="true">
            {expanded ? "expand_less" : "expand_more"}
          </span>
        ) : null}
      </div>
      {expanded ? (
        <div
          id="agent-activity-panel"
          className="agent-activity-panel"
          ref={panelRef}
          data-testid="agent-activity-panel"
          role="log"
          aria-label="Agent activity"
        >
          {activityLog.length === 0 ? (
            <div className="agent-activity-empty">Waiting for agent events…</div>
          ) : (
            activityLog.map((entry, index) => (
              <div
                key={`${entry.t}-${entry.kind}-${index}`}
                className={`agent-activity-row kind-${entry.kind}`}
                data-testid="agent-activity-row"
                data-kind={entry.kind}
              >
                <span className="material-symbols-outlined agent-activity-icon" aria-hidden="true">
                  {kindIcon(entry.kind)}
                </span>
                <div className="agent-activity-body">
                  <span className="agent-activity-label">{entry.label}</span>
                  {entry.detail ? <span className="agent-activity-detail">{entry.detail}</span> : null}
                </div>
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
