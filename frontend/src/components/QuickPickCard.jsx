import { useState } from "react";
import TitleCard from "./TitleCard";

export default function QuickPickCard({
  item,
  why,
  status = "ready",
  message,
  loading = false,
  onRetry,
  onTellMore,
  onAdd,
  onDismiss,
  requestPath = "arr",
  userRole,
  multiUserEnabled = true,
}) {
  const [revealed, setRevealed] = useState(false);

  if (loading) {
    return (
      <div className="quick-pick-card quick-pick-status" data-testid="quick-pick-loading" role="status">
        <span className="quick-pick-badge">Surprise me</span>
        <p className="quick-pick-status-message">Picking something from your library…</p>
      </div>
    );
  }

  if (status === "error" || status === "empty" || !item) {
    const isError = status === "error";
    return (
      <div
        className={`quick-pick-card quick-pick-status ${isError ? "is-error" : "is-empty"}`}
        data-testid={isError ? "quick-pick-error" : "quick-pick-empty"}
        role="status"
      >
        <span className="quick-pick-badge">{isError ? "Couldn't pick" : "Nothing to surprise"}</span>
        <p className="quick-pick-status-message">
          {message || (isError ? "Couldn't pick a title right now." : "No unwatched titles match the criteria.")}
        </p>
        <div className="quick-pick-actions">
          {onRetry ? (
            <button type="button" className="ghost quick-pick-retry" onClick={onRetry} data-testid="quick-pick-retry">
              Try again
            </button>
          ) : null}
          {onDismiss ? (
            <button
              type="button"
              className="ghost quick-pick-dismiss"
              onClick={onDismiss}
              data-testid="quick-pick-dismiss"
            >
              Dismiss
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`quick-pick-card ${revealed ? "revealed" : "revealing"}`}
      data-testid="quick-pick-card"
      onAnimationEnd={() => setRevealed(true)}
    >
      <span className="quick-pick-badge" data-testid="quick-pick-badge">
        Picked for you
      </span>
      <TitleCard
        item={item}
        onAdd={onAdd}
        onDismiss={onDismiss}
        requestPath={requestPath}
        userRole={userRole}
        multiUserEnabled={multiUserEnabled}
      />
      {why ? <p className="quick-pick-why">{why}</p> : null}
      <div className="quick-pick-actions">
        {onRetry ? (
          <button type="button" className="ghost quick-pick-retry" onClick={onRetry} data-testid="quick-pick-retry">
            Try again
          </button>
        ) : null}
        {onTellMore ? (
          <button type="button" className="ghost quick-pick-more" onClick={onTellMore} data-testid="quick-pick-more">
            Tell me more
          </button>
        ) : null}
      </div>
    </div>
  );
}
