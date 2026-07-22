import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  dedupeNotifications,
  inboxHeadline,
  normalizeRecommendation,
} from "../lib/recommendationInbox.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import PosterOverlayControls from "./PosterOverlayControls";

function cardLead(rec) {
  const kind = String(rec.kind || "recommendation");
  const fromName = rec.from_display_name || "Someone";
  const yearBit = rec.year ? ` (${rec.year})` : "";
  if (kind === "arrival") {
    return (
      <>
        <strong>Now available</strong> — <em>{rec.title}{yearBit}</em>
      </>
    );
  }
  if (kind === "digest") {
    return <strong>{rec.title || "Digest"}</strong>;
  }
  if (kind === "access-request") {
    return (
      <>
        <strong>Access request</strong> — {rec.title || "New request"}
      </>
    );
  }
  if (kind === "nudge") {
    return (
      <>
        <strong>Nudge</strong> — {rec.title || "Something to see"}
      </>
    );
  }
  return (
    <>
      <strong>{fromName}</strong> recommended{" "}
      <em>
        {rec.title}
        {yearBit}
      </em>{" "}
      for you
    </>
  );
}

export default function RecommendationsInbox({ items = [], onDismiss, onDismissAll }) {
  const recommendations = useMemo(() => dedupeNotifications(items), [items]);
  if (!recommendations.length) return null;

  return (
    <section
      className="recommendations-inbox"
      data-testid="recommendations-inbox"
      aria-label="Notifications inbox"
      id="notifications-inbox"
    >
      <header className="recommendations-inbox-header">
        <div>
          <p className="eyebrow">For you</p>
          <h2>{inboxHeadline(recommendations)}</h2>
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
          const note = rec.message || rec.body;
          const kind = String(rec.kind || "recommendation");
          const showPoster = Boolean(rec.poster_url) || kind === "recommendation" || kind === "arrival";
          return (
            <article
              key={rec.id}
              className={`recommendation-card recommendation-card--${kind}`}
              data-testid={`recommendation-card-${rec.id}`}
              data-kind={kind}
              style={{ zIndex: recommendations.length - index }}
            >
              {showPoster ? (
                <div className="recommendation-card-poster">
                  {rec.poster_url ? (
                    <img src={rec.poster_url} alt="" loading="lazy" />
                  ) : (
                    <div className="poster-fallback">{(rec.title || "?").slice(0, 1)}</div>
                  )}
                  {kind === "recommendation" || kind === "arrival" ? (
                    <PosterOverlayControls item={recommendation} testPrefix="recommendation" />
                  ) : null}
                </div>
              ) : null}
              <div className="recommendation-card-body">
                <p className="recommendation-card-from">{cardLead(rec)}</p>
                {note ? <p className="recommendation-card-note">“{note}”</p> : null}
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
