import { Link } from "react-router-dom";
import { relativeTime } from "../api/client";
import { titleDetailPath } from "../lib/titleLinks.js";

export default function WatchlistPanel({ pins = [], open, onToggle, onRemove }) {
  if (!pins.length) return null;

  return (
    <div className="watchlist-panel" data-testid="watchlist-panel">
      <button
        type="button"
        className="watchlist-panel-toggle ghost"
        data-testid="watchlist-panel-toggle"
        onClick={onToggle}
        aria-expanded={open}
      >
        Watchlist ({pins.length})
      </button>
      {open ? (
        <ul className="watchlist-panel-list">
          {pins.map((pin) => {
            const detailPath = titleDetailPath(pin);
            const body = (
              <>
                <span className="watchlist-panel-title">{pin.title}</span>
                <span className="watchlist-panel-meta">
                  {pin.media_type === "show" ? "Show" : "Movie"} · {relativeTime(pin.created_at)}
                </span>
              </>
            );
            return (
              <li key={pin.id} className="watchlist-panel-item">
                {detailPath ? (
                  <Link
                    to={detailPath}
                    className="watchlist-panel-item-body watchlist-panel-item-link"
                    data-testid={`watchlist-open-${pin.id}`}
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="watchlist-panel-item-body">{body}</div>
                )}
                <button
                  type="button"
                  className="ghost watchlist-panel-remove"
                  data-testid={`watchlist-remove-${pin.id}`}
                  onClick={() => onRemove?.(pin)}
                  aria-label={`Remove ${pin.title} from watchlist`}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
