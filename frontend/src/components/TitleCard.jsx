import { useState } from "react";
import { setTitleCardDragData } from "../lib/easterEggs.js";
import { displayRecommendationReason } from "../lib/recommendationReason.js";
import { allowWatchlistPin } from "../lib/watchlistPin.js";

function ShowProgressRing({ total, unwatched }) {
  if (!total || total <= 0) return null;
  const watched = Math.max(0, total - (unwatched ?? 0));
  const pct = Math.min(1, watched / total);
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - pct);

  return (
    <svg
      className="title-card-progress-ring"
      viewBox="0 0 32 32"
      aria-hidden="true"
      data-testid="title-card-progress-ring"
    >
      <circle className="title-card-progress-track" cx="16" cy="16" r={radius} />
      <circle
        className="title-card-progress-fill"
        cx="16"
        cy="16"
        r={radius}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
      />
    </svg>
  );
}

export default function TitleCard({
  item,
  onAdd,
  onDismiss,
  onTogglePin,
  pinRecord = null,
  compact = false,
  requestPath = "arr",
  draggableToDock = false,
}) {
  const [hovered, setHovered] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  const badge = item.in_library ? "In library" : item.in_radarr || item.in_sonarr ? "In queue" : "New";
  const userStars = item.user_stars;
  const useSeerr = requestPath === "seerr";
  const canRequestSeerr = useSeerr && !item.in_library && item.tmdb_id;
  const canAddRadarr = !useSeerr && !item.in_library && item.media_type === "movie" && item.tmdb_id;
  const canAddSonarr = !useSeerr && !item.in_library && item.media_type === "show" && item.tvdb_id;
  const backdropUrl = item.backdrop_url || item.art || "";
  const showRing =
    item.media_type === "show" &&
    (item.total_episode_count > 0 || item.unwatched_episode_count != null);
  const isPinned = Boolean(pinRecord);
  const showPin = Boolean(onTogglePin) && allowWatchlistPin(item);
  const facetMatches = item.facet_matches || [];
  const whyReason = displayRecommendationReason(item.recommendation_reason);
  const hasWhyDetail = Boolean(whyReason || facetMatches.length);

  function handleDragStart(event) {
    if (!draggableToDock) return;
    setTitleCardDragData(event, item);
  }

  function handleAdd(target) {
    return (event) => {
      event.stopPropagation();
      onAdd?.(item, target);
    };
  }

  function handleDismiss(event) {
    event.stopPropagation();
    onDismiss?.(item);
  }

  function handleTogglePin(event) {
    event.stopPropagation();
    onTogglePin?.(item, pinRecord);
  }

  const addActions = (
    <>
      {canRequestSeerr ? (
        <button type="button" data-testid="request-seerr-button" onClick={handleAdd("seerr")}>
          Request in Seerr
        </button>
      ) : null}
      {canAddRadarr ? (
        <button type="button" data-testid="add-radarr-button" onClick={handleAdd("radarr")}>
          Add to Radarr
        </button>
      ) : null}
      {canAddSonarr ? (
        <button type="button" data-testid="add-sonarr-button" onClick={handleAdd("sonarr")}>
          Add to Sonarr
        </button>
      ) : null}
    </>
  );

  return (
    <article
      className={`title-card ${compact ? "compact" : ""} ${hovered && backdropUrl ? "has-hover-backdrop" : ""}`}
      data-testid="title-card"
      draggable={draggableToDock}
      onDragStart={handleDragStart}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {hovered && backdropUrl ? (
        <div
          className="title-card-hover-backdrop"
          style={{ backgroundImage: `url(${backdropUrl})` }}
          aria-hidden="true"
        />
      ) : null}
      <div className="poster-wrap">
        {item.poster_url ? (
          <img src={item.poster_url} alt="" loading="lazy" />
        ) : (
          <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
        )}
        <span className="badge">{badge}</span>
        {userStars ? (
          <span className="user-review-badge" data-testid="user-review-badge" title={`You rated ${userStars}/5`}>
            {Number(userStars) % 1 === 0 ? "★".repeat(userStars) : `${userStars}★`}
          </span>
        ) : null}
        {showRing ? (
          <ShowProgressRing
            total={item.total_episode_count}
            unwatched={item.unwatched_episode_count}
          />
        ) : null}
        {showPin ? (
          <button
            type="button"
            className={`title-card-pin ${isPinned ? "pinned" : ""}`}
            data-testid="title-card-pin"
            onClick={handleTogglePin}
            aria-label={isPinned ? "Remove from watchlist" : "Pin to watchlist"}
            title={isPinned ? "Remove from watchlist" : "Pin to watchlist"}
          >
            {isPinned ? "★" : "☆"}
          </button>
        ) : null}
        {compact && (canRequestSeerr || canAddRadarr || canAddSonarr) ? (
          <div className="title-card-overlay-actions">{addActions}</div>
        ) : null}
      </div>
      <div className="card-body">
        <h3>
          {item.title || "Unknown title"}
          {item.year ? <span className="year"> ({item.year})</span> : null}
        </h3>
        {item.rating ? <p className="rating">★ {item.rating.toFixed(1)}</p> : null}
        {userStars ? <p className="user-review-stars" data-testid="user-review-stars">Your rating: {Number(userStars) % 1 === 0 ? "★".repeat(userStars) : `${userStars}★`}</p> : null}
        {item.genres?.length ? <p className="genres">{item.genres.slice(0, 3).join(" · ")}</p> : null}
        {!compact && item.overview ? <p className="overview">{item.overview.slice(0, 160)}…</p> : null}
        {whyReason && !whyOpen ? <p className="reason">{whyReason}</p> : null}
        {hasWhyDetail ? (
          <div className="title-card-why">
            <button
              type="button"
              className="ghost title-card-why-toggle"
              data-testid="title-card-why-toggle"
              onClick={(event) => {
                event.stopPropagation();
                setWhyOpen((open) => !open);
              }}
            >
              {whyOpen ? "Hide why" : "Why this?"}
            </button>
            {whyOpen ? (
              <div className="title-card-why-detail" data-testid="title-card-why-detail">
                {whyReason ? <p>{whyReason}</p> : null}
                {facetMatches.length ? (
                  <ul>
                    {facetMatches.map((match) => (
                      <li key={match}>{match}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="card-actions">
          {!compact ? addActions : null}
          {!compact ? (
            <button type="button" className="ghost" onClick={handleDismiss}>
              Not interested
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}
