import { useState } from "react";
import TitleCard from "./TitleCard";

export default function QuickPickCard({ item, why, onRetry, onTellMore, onAdd, onDismiss, requestPath = "arr" }) {
  const [revealed, setRevealed] = useState(false);

  if (!item) return null;

  return (
    <div
      className={`quick-pick-card ${revealed ? "revealed" : "revealing"}`}
      data-testid="quick-pick-card"
      onAnimationEnd={() => setRevealed(true)}
    >
      <span className="quick-pick-badge" data-testid="quick-pick-badge">Picked for you</span>
      <TitleCard item={item} onAdd={onAdd} onDismiss={onDismiss} requestPath={requestPath} />
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
