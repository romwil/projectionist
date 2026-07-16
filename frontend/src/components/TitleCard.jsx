import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getPlexMachineId } from "../api/client";
import { setTitleCardDragData } from "../lib/easterEggs.js";
import { displayRecommendationReason } from "../lib/recommendationReason.js";
import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "../lib/titleLinks.js";
import { allowWatchlistPin } from "../lib/watchlistPin.js";

let cachedPlexMachineId;
let plexMachineIdPromise;

function loadPlexMachineId() {
  if (cachedPlexMachineId !== undefined) {
    return Promise.resolve(cachedPlexMachineId);
  }
  if (!plexMachineIdPromise) {
    plexMachineIdPromise = getPlexMachineId()
      .then((machineId) => {
        cachedPlexMachineId = machineId;
        return cachedPlexMachineId;
      })
      .catch(() => {
        cachedPlexMachineId = "";
        return "";
      });
  }
  return plexMachineIdPromise;
}

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
  onRecommend,
  pinRecord = null,
  compact = false,
  requestPath = "arr",
  draggableToDock = false,
}) {
  const [hovered, setHovered] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  const [plexHref, setPlexHref] = useState(() => String(item?.plex_watch_url || "").trim());
  const badge = item.in_library ? "In library" : item.in_radarr || item.in_sonarr ? "In queue" : "New";
  const userStars = item.user_stars;
  const useSeerr = requestPath === "seerr";
  const canRequestSeerr = useSeerr && !item.in_library && item.tmdb_id;
  const canAddRadarr = !useSeerr && !item.in_library && item.media_type === "movie" && item.tmdb_id;
  const canAddSonarr = !useSeerr && !item.in_library && item.media_type === "show" && item.tvdb_id;
  const showWatchPlex = canWatchOnPlex(item);
  const backdropUrl = item.backdrop_url || item.art || "";
  const showRing =
    item.media_type === "show" &&
    (item.total_episode_count > 0 || item.unwatched_episode_count != null);
  const isPinned = Boolean(pinRecord);
  const showPin = Boolean(onTogglePin) && allowWatchlistPin(item);
  const facetMatches = item.facet_matches || [];
  const whyReason = displayRecommendationReason(item.recommendation_reason);
  const hasWhyDetail = Boolean(whyReason || facetMatches.length);
  const detailPath = titleDetailPath(item);
  const titleLabel = `${item.title || "Unknown title"}${item.year ? ` (${item.year})` : ""}`;

  useEffect(() => {
    const provided = String(item?.plex_watch_url || "").trim();
    if (provided) {
      setPlexHref(provided);
      return;
    }
    if (!showWatchPlex) {
      setPlexHref("");
      return;
    }
    let cancelled = false;
    loadPlexMachineId().then((machineId) => {
      if (cancelled) return;
      setPlexHref(plexWatchUrl(item.rating_key, machineId));
    });
    return () => {
      cancelled = true;
    };
  }, [item?.plex_watch_url, item?.rating_key, showWatchPlex]);

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

  function handleRecommend(event) {
    event.stopPropagation();
    onRecommend?.(item);
  }

  const watchPlexAction =
    showWatchPlex && plexHref ? (
      <a
        href={plexHref}
        className="btn-link title-card-plex-link"
        data-testid="watch-on-plex-button"
        target="_blank"
        rel="noopener noreferrer"
        onClick={(event) => event.stopPropagation()}
      >
        Watch on Plex
      </a>
    ) : null;

  const addActions = (
    <>
      {watchPlexAction}
      {onRecommend ? (
        <button type="button" className="ghost" data-testid="recommend-title-button" onClick={handleRecommend}>
          Recommend
        </button>
      ) : null}
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

  const posterMedia = item.poster_url ? (
    <img src={item.poster_url} alt="" loading="lazy" />
  ) : (
    <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
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
        {detailPath ? (
          <Link
            to={detailPath}
            className="title-card-poster-link"
            data-testid="title-card-detail-link"
            aria-label={`Open details for ${titleLabel}`}
          >
            {posterMedia}
          </Link>
        ) : (
          posterMedia
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
        {compact && (watchPlexAction || onRecommend || canRequestSeerr || canAddRadarr || canAddSonarr) ? (
          <div className="title-card-overlay-actions">{addActions}</div>
        ) : null}
      </div>
      <div className="card-body">
        <h3>
          {detailPath ? (
            <Link to={detailPath} className="title-card-title-link" data-testid="title-card-title-link">
              {item.title || "Unknown title"}
              {item.year ? <span className="year"> ({item.year})</span> : null}
            </Link>
          ) : (
            <>
              {item.title || "Unknown title"}
              {item.year ? <span className="year"> ({item.year})</span> : null}
            </>
          )}
        </h3>
        {item.rating ? <p className="rating">★ {item.rating.toFixed(1)}</p> : null}
        {userStars ? <p className="user-review-stars" data-testid="user-review-stars">Your rating: {Number(userStars) % 1 === 0 ? "★".repeat(userStars) : `${userStars}★`}</p> : null}
        {item.genres?.length ? <p className="genres">{item.genres.slice(0, 3).join(" · ")}</p> : null}
        {item.runtime_minutes ? (
          <p className={`runtime ${item.runtime_minutes < 100 ? "runtime-emphasis" : ""}`}>
            {item.runtime_minutes} min
          </p>
        ) : null}
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
