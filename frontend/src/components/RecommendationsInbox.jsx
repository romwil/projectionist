import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  dedupeNotifications,
  digestBlurb,
  digestPicks,
  eventPrimaryCta,
  inboxHeadline,
  isEnthusiastNudge,
  isLiveChannelsNudge,
  isWatchPartyRecommendation,
  normalizeRecommendation,
  nudgeCardNote,
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

function cardLead(rec, recommendation, picks) {
  const kind = String(rec.kind || "recommendation");
  const fromName = rec.from_display_name || "Someone";
  const yearBit = rec.year ? ` (${rec.year})` : "";
  if (kind === "arrival") {
    return (
      <>
        <strong>Now in your library</strong> —{" "}
        <TitleDigInEm item={recommendation}>
          {rec.title}
          {yearBit}
        </TitleDigInEm>
      </>
    );
  }
  if (kind === "digest") {
    const count = picks.length;
    if (count > 0) {
      return (
        <>
          <strong>This week for you</strong>
          <span className="recommendation-pick-count">
            {" "}
            · {`${count} pick${count === 1 ? "" : "s"}`}
          </span>
        </>
      );
    }
    return <strong>{rec.title || "This week for you"}</strong>;
  }
  if (kind === "access-request") {
    const name = rec.payload?.display_name || rec.title?.replace(/^Access request from\s+/i, "") || "Someone";
    return (
      <>
        <strong>{name}</strong> wants access
      </>
    );
  }
  if (kind === "nudge") {
    if (isLiveChannelsNudge(rec)) {
      return <strong>Live Channels ready</strong>;
    }
    const mediaTitle = recommendationMediaTitle(rec) || rec.title || "this title";
    return (
      <>
        <strong>You have to see this</strong> —{" "}
        <TitleDigInEm item={recommendation}>
          {mediaTitle}
          {yearBit}
        </TitleDigInEm>
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

function DigestPickStrip({ picks, recId, onOpen }) {
  if (!picks.length) return null;
  return (
    <ul
      className="recommendation-pick-strip"
      data-testid={`recommendation-pick-strip-${recId}`}
      aria-label="Digest picks"
    >
      {picks.map((pick, index) => {
        const key = `${pick.tmdb_id || pick.rating_key || pick.tvdb_id || pick.title}-${index}`;
        const path = titleDetailPath(pick);
        const inner = pick.poster_url ? (
          <img src={pick.poster_url} alt="" loading="lazy" />
        ) : (
          <div className="poster-fallback">{(pick.title || "?").slice(0, 1)}</div>
        );
        return (
          <li key={key} className="recommendation-pick-chip">
            {path ? (
              <TitleDetailLink
                item={pick}
                className="recommendation-pick-link"
                aria-label={`Open ${pick.title}`}
                data-testid={`recommendation-pick-${recId}-${index}`}
                onClick={() => onOpen?.(pick)}
              >
                {inner}
                <span className="recommendation-pick-title">{pick.title}</span>
              </TitleDetailLink>
            ) : (
              <span className="recommendation-pick-link recommendation-pick-link--inert">
                {inner}
                <span className="recommendation-pick-title">{pick.title}</span>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function DigestCardBody({ rec, onDismiss }) {
  const picks = digestPicks(rec);
  const blurb = digestBlurb(rec);
  const fullNote = String(rec.body || rec.message || "").trim();
  const showDisclosure = Boolean(fullNote && fullNote !== blurb);
  const [openNote, setOpenNote] = useState(false);
  const primaryPick = picks[0] || null;
  const chatHref = primaryPick ? chatAboutTitleHref(primaryPick) : null;

  return (
    <>
      {blurb ? (
        <p className="recommendation-card-blurb" data-testid={`recommendation-blurb-${rec.id}`}>
          {blurb}
        </p>
      ) : null}
      <DigestPickStrip picks={picks} recId={rec.id} onOpen={() => onDismiss?.(rec)} />
      {showDisclosure ? (
        <details
          className="recommendation-curator-note"
          data-testid={`recommendation-curator-note-${rec.id}`}
          open={openNote}
          onToggle={(event) => setOpenNote(event.currentTarget.open)}
        >
          <summary>Read curator note</summary>
          <p className="recommendation-card-note recommendation-card-note--full">“{fullNote}”</p>
        </details>
      ) : null}
      <div className="recommendation-card-actions">
        {primaryPick && titleDetailPath(primaryPick) ? (
          <TitleDetailLink
            item={primaryPick}
            className="btn-link recommendation-cta-primary"
            data-testid={`recommendation-open-${rec.id}`}
            onClick={() => onDismiss?.(rec)}
          >
            Open picks
          </TitleDetailLink>
        ) : null}
        {chatHref ? (
          <Link
            to={chatHref}
            className="btn-link"
            data-testid={`recommendation-chat-${rec.id}`}
            onClick={() => onDismiss?.(rec)}
          >
            Chat about this week
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
    </>
  );
}

export default function RecommendationsInbox({ items = [], onDismiss, onDismissAll, role }) {
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
          const kind = String(rec.kind || "recommendation");
          const picks = kind === "digest" ? digestPicks(rec) : [];
          const watchParty = kind === "recommendation" && isWatchPartyRecommendation(rec);
          const primaryCta = eventPrimaryCta(rec, { role });
          const showPoster =
            Boolean(rec.poster_url) ||
            kind === "recommendation" ||
            kind === "arrival" ||
            (kind === "nudge" && isEnthusiastNudge(rec) && Boolean(rec.poster_url || path));
          const mediaTitle =
            kind === "recommendation" || isEnthusiastNudge(rec)
              ? recommendationMediaTitle(rec)
              : rec.title;
          const chatHref =
            kind === "recommendation" && mediaTitle ? chatAboutTitleHref(recommendation) : null;
          const note =
            kind === "digest"
              ? null
              : kind === "nudge"
                ? nudgeCardNote(rec)
                : kind === "access-request"
                  ? null
                  : rec.message || rec.body;
          const cardClass = [
            "recommendation-card",
            "recommendation-card--event",
            `recommendation-card--${kind}`,
            watchParty ? "recommendation-card--watch-party" : "",
            isLiveChannelsNudge(rec) ? "recommendation-card--live-nudge" : "",
            isEnthusiastNudge(rec) ? "recommendation-card--enthusiast-nudge" : "",
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
              style={{ zIndex: recommendations.length - index, animationDelay: `${Math.min(index, 6) * 40}ms` }}
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
                <p className="recommendation-card-from">{cardLead(rec, recommendation, picks)}</p>
                {kind === "digest" ? (
                  <DigestCardBody rec={rec} onDismiss={onDismiss} />
                ) : (
                  <>
                    {note ? (
                      <p className="recommendation-card-blurb" data-testid={`recommendation-blurb-${rec.id}`}>
                        {note}
                      </p>
                    ) : null}
                    <div className="recommendation-card-actions">
                      {primaryCta ? (
                        <Link
                          to={primaryCta.href}
                          className="btn-link recommendation-cta-primary"
                          data-testid={`recommendation-${primaryCta.testIdSuffix}-${rec.id}`}
                          onClick={() => onDismiss?.(rec)}
                        >
                          {primaryCta.label}
                        </Link>
                      ) : null}
                      {!primaryCta && path ? (
                        <TitleDetailLink
                          item={recommendation}
                          className="btn-link recommendation-cta-primary"
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
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
