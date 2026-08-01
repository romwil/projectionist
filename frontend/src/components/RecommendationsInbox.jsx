import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  dedupeNotifications,
  inboxHeadline,
  isWatchPartyRecommendation,
  normalizeRecommendation,
  recommendationMediaTitle,
} from "../lib/recommendationInbox.js";
import { chatAboutTitleHref } from "../lib/backNav.js";
import { titleDetailPath } from "../lib/titleLinks.js";
import PosterOverlayControls from "./PosterOverlayControls";
import TitleDetailLink from "./TitleDetailLink";

function TitleDigInEm({ item, children }) {
  if (!item || !titleDetailPath(item)) return <em>{children}</em>;
  return (
    <em>
      <TitleDetailLink item={item} className="recommendation-title-link">
        {children}
      </TitleDetailLink>
    </em>
  );
}

function cardLead(rec, recommendation) {
  const kind = String(rec.kind || "recommendation");
  const fromName = rec.from_display_name || "Someone";
  const yearBit = rec.year ? ` (${rec.year})` : "";
  if (kind === "arrival") {
    return (
      <>
        <strong>Now available</strong> —{" "}
        <TitleDigInEm item={recommendation}>
          {rec.title}
          {yearBit}
        </TitleDigInEm>
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
  if (kind === "library-share") {
    return (
      <>
        <strong>{fromName}</strong> shared a saved page — <em>{rec.title || "Library page"}</em>
      </>
    );
  }
  const mediaTitle = recommendationMediaTitle(rec);
  if (isWatchPartyRecommendation(rec)) {
    return (
      <>
        <span className="recommendation-watch-party-badge" data-testid="recommendation-watch-party-badge">
          Watch together
        </span>{" "}
        <strong>{fromName}</strong> invited you to watch{" "}
        <TitleDigInEm item={recommendation}>
          {mediaTitle}
          {yearBit}
        </TitleDigInEm>
      </>
    );
  }
  return (
    <>
      <strong>{fromName}</strong> recommended{" "}
      <TitleDigInEm item={recommendation}>
        {mediaTitle}
        {yearBit}
      </TitleDigInEm>{" "}
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
          const watchParty = kind === "recommendation" && isWatchPartyRecommendation(rec);
          const librarySharePath =
            kind === "library-share"
              ? rec.payload?.path ||
                (rec.payload?.page_id ? `/library/${encodeURIComponent(rec.payload.page_id)}` : null)
              : null;
          const showPoster =
            Boolean(rec.poster_url) || kind === "recommendation" || kind === "arrival";
          const mediaTitle = kind === "recommendation" ? recommendationMediaTitle(rec) : rec.title;
          const chatHref =
            kind === "recommendation" && mediaTitle ? chatAboutTitleHref(recommendation) : null;
          const cardClass = [
            "recommendation-card",
            `recommendation-card--${kind}`,
            watchParty ? "recommendation-card--watch-party" : "",
            showPoster ? "" : "recommendation-card--text-only",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <article
              key={rec.id}
              className={cardClass}
              data-testid={`recommendation-card-${rec.id}`}
              data-kind={kind}
              data-intent={watchParty ? "watch_party" : recommendation.intent || undefined}
              style={{ zIndex: recommendations.length - index }}
            >
              {showPoster ? (
                <div className="recommendation-card-poster">
                  {path ? (
                    <TitleDetailLink
                      item={recommendation}
                      className="recommendation-poster-link"
                      aria-label={`Open details for ${mediaTitle || "title"}`}
                    >
                      {rec.poster_url ? (
                        <img src={rec.poster_url} alt="" loading="lazy" />
                      ) : (
                        <div className="poster-fallback">{(mediaTitle || "?").slice(0, 1)}</div>
                      )}
                    </TitleDetailLink>
                  ) : rec.poster_url ? (
                    <img src={rec.poster_url} alt="" loading="lazy" />
                  ) : (
                    <div className="poster-fallback">{(mediaTitle || "?").slice(0, 1)}</div>
                  )}
                  {kind === "recommendation" || kind === "arrival" ? (
                    <PosterOverlayControls item={recommendation} testPrefix="recommendation" />
                  ) : null}
                </div>
              ) : null}
              <div className="recommendation-card-body">
                {rec.from_display_name && (kind === "recommendation" || kind === "library-share") ? (
                  <p className="recommendation-card-from-meta">
                    {rec.from_avatar_url ? (
                      <img
                        src={rec.from_avatar_url}
                        alt=""
                        className="recommendation-from-avatar"
                        loading="lazy"
                      />
                    ) : (
                      <span className="recommendation-from-avatar recommendation-from-avatar--fallback" aria-hidden="true">
                        {String(rec.from_display_name).slice(0, 1)}
                      </span>
                    )}
                    <span>{rec.from_display_name}</span>
                  </p>
                ) : null}
                <p className="recommendation-card-from">{cardLead(rec, recommendation)}</p>
                {note ? <p className="recommendation-card-note">“{note}”</p> : null}
                <div className="recommendation-card-actions">
                  {librarySharePath ? (
                    <Link
                      to={librarySharePath}
                      className="btn-link"
                      data-testid={`recommendation-open-library-${rec.id}`}
                      onClick={() => onDismiss?.(rec)}
                    >
                      Open saved page
                    </Link>
                  ) : null}
                  {path ? (
                    <TitleDetailLink
                      item={recommendation}
                      className="btn-link"
                      data-testid={`recommendation-open-${rec.id}`}
                      onClick={() => onDismiss?.(rec)}
                    >
                      Open title
                    </TitleDetailLink>
                  ) : null}
                  {chatHref ? (
                    <Link
                      to={chatHref}
                      className="btn-link"
                      data-testid={`recommendation-chat-${rec.id}`}
                      onClick={() => onDismiss?.(rec)}
                    >
                      Chat about this
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
