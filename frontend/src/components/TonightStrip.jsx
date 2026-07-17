import { Link } from "react-router-dom";
import { titleDetailPath } from "../lib/titleLinks.js";

/** Compact 1–3 tonight picks above the composer (non-blocking). */
export default function TonightStrip({
  items = [],
  loading = false,
  onDismiss,
  onPick,
}) {
  if (loading && !items.length) {
    return (
      <div className="tonight-strip tonight-strip-loading" data-testid="tonight-strip" role="status">
        <p className="tonight-strip-label">Tonight</p>
        <p className="status status-secondary">Finding a few picks…</p>
      </div>
    );
  }

  if (!items.length) return null;

  return (
    <div className="tonight-strip" data-testid="tonight-strip">
      <div className="tonight-strip-header">
        <p className="tonight-strip-label">Tonight</p>
        {onDismiss ? (
          <button
            type="button"
            className="ghost tonight-strip-dismiss"
            data-testid="tonight-strip-dismiss"
            onClick={onDismiss}
          >
            Hide
          </button>
        ) : null}
      </div>
      <ul className="tonight-strip-list">
        {items.map((item) => {
          const path = titleDetailPath({ ...item, in_library: true });
          const body = (
            <>
              <span className="tonight-strip-poster">
                {item.poster_url ? (
                  <img src={item.poster_url} alt="" loading="lazy" />
                ) : (
                  <span className="poster-fallback">{(item.title || "?").slice(0, 1)}</span>
                )}
              </span>
              <span className="tonight-strip-copy">
                <span className="tonight-strip-title">{item.title || "Untitled"}</span>
                {item.year || item.runtime_minutes ? (
                  <span className="tonight-strip-meta">
                    {[item.year, item.runtime_minutes ? `${item.runtime_minutes}m` : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                ) : null}
              </span>
            </>
          );
          return (
            <li key={`${item.media_type}-${item.tmdb_id || item.rating_key || item.title}`}>
              {path ? (
                <Link
                  to={path}
                  className="tonight-strip-card"
                  data-testid="tonight-strip-item"
                  onClick={() => onPick?.(item)}
                >
                  {body}
                </Link>
              ) : (
                <button
                  type="button"
                  className="tonight-strip-card"
                  data-testid="tonight-strip-item"
                  onClick={() => onPick?.(item)}
                >
                  {body}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
