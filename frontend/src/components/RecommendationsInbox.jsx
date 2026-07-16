import { Link } from "react-router-dom";
import { titleDetailPath } from "../lib/titleLinks.js";

export default function RecommendationsInbox({ items = [], onDismiss, onDismissAll }) {
  if (!items.length) return null;

  return (
    <section className="recommendations-inbox" data-testid="recommendations-inbox" aria-label="New recommendations">
      <header className="recommendations-inbox-header">
        <div>
          <p className="eyebrow">For you</p>
          <h2>{items.length === 1 ? "Someone recommended a title" : `${items.length} new recommendations`}</h2>
        </div>
        {items.length > 1 ? (
          <button
            type="button"
            className="ghost"
            data-testid="recommendations-dismiss-all"
            onClick={() => onDismissAll?.(items)}
          >
            Dismiss all
          </button>
        ) : null}
      </header>
      <div className="recommendations-inbox-stack">
        {items.map((rec, index) => {
          const path = titleDetailPath({
            media_type: rec.media_type,
            tmdb_id: rec.tmdb_id,
            tvdb_id: rec.tvdb_id,
            rating_key: rec.rating_key,
          });
          const fromName = rec.from_display_name || "Someone";
          const yearBit = rec.year ? ` (${rec.year})` : "";
          return (
            <article
              key={rec.id}
              className="recommendation-card"
              data-testid={`recommendation-card-${rec.id}`}
              style={{ zIndex: items.length - index }}
            >
              <div className="recommendation-card-poster">
                {rec.poster_url ? (
                  <img src={rec.poster_url} alt="" loading="lazy" />
                ) : (
                  <div className="poster-fallback">{(rec.title || "?").slice(0, 1)}</div>
                )}
              </div>
              <div className="recommendation-card-body">
                <p className="recommendation-card-from">
                  <strong>{fromName}</strong> recommended{" "}
                  <em>
                    {rec.title}
                    {yearBit}
                  </em>{" "}
                  for you
                </p>
                {rec.message ? <p className="recommendation-card-note">“{rec.message}”</p> : null}
                <div className="recommendation-card-actions">
                  {path ? (
                    <Link
                      to={path}
                      className="btn-link"
                      data-testid={`recommendation-open-${rec.id}`}
                      onClick={() => onDismiss?.(rec)}
                    >
                      Open title
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className="ghost"
                    data-testid={`recommendation-dismiss-${rec.id}`}
                    onClick={() => onDismiss?.(rec)}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
