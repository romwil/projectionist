import { useMemo } from "react";
import { Link } from "react-router-dom";
import { dedupeRecommendations, normalizeRecommendation } from "../lib/recommendationInbox.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import PosterOverlayControls from "./PosterOverlayControls";

export default function RecommendationsInbox({ items = [], onDismiss, onDismissAll }) {
  const recommendations = useMemo(() => dedupeRecommendations(items), [items]);
  if (!recommendations.length) return null;

  return (
    <section className="recommendations-inbox" data-testid="recommendations-inbox" aria-label="New recommendations">
      <header className="recommendations-inbox-header">
        <div>
          <p className="eyebrow">For you</p>
          <h2>{recommendations.length === 1 ? "Someone recommended a title" : `${recommendations.length} new recommendations`}</h2>
        </div>
        {recommendations.length > 1 ? (
          <button
            type="button"
            className="ghost"
            data-testid="recommendations-dismiss-all"
            onClick={() => onDismissAll?.(recommendations)}
          >
            Dismiss all
          </button>
        ) : null}
      </header>
      <div className="recommendations-inbox-stack">
        {recommendations.map((rec, index) => {
          const recommendation = normalizeRecommendation(rec);
          const path = titleDetailPath(recommendation);
          const fromName = rec.from_display_name || "Someone";
          const yearBit = rec.year ? ` (${rec.year})` : "";
          return (
            <article
              key={rec.id}
              className="recommendation-card"
              data-testid={`recommendation-card-${rec.id}`}
              style={{ zIndex: recommendations.length - index }}
            >
              <div className="recommendation-card-poster">
                {rec.poster_url ? (
                  <img src={rec.poster_url} alt="" loading="lazy" />
                ) : (
                  <div className="poster-fallback">{(rec.title || "?").slice(0, 1)}</div>
                )}
                <PosterOverlayControls item={recommendation} testPrefix="recommendation" />
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
