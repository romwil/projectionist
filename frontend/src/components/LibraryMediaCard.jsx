import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getPlexMachineId } from "../api/client";
import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "../lib/titleLinks.js";

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

/**
 * Explore / tag / plot-lab poster card with hover Watch / Trailer / Recommend.
 */
export default function LibraryMediaCard({
  item,
  meta,
  onSeed,
  seedLabel = "Surprise from this",
  onRecommend,
  showRecommend = false,
  testId = "explore-title-card",
}) {
  const [hovered, setHovered] = useState(false);
  const [plexHref, setPlexHref] = useState(() => String(item?.plex_watch_url || "").trim());
  const [trailerKey, setTrailerKey] = useState(() => String(item?.trailer_youtube_key || "").trim());
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [trailerLoading, setTrailerLoading] = useState(false);

  const path = titleDetailPath({ ...item, in_library: true });
  const showWatch = canWatchOnPlex(item);

  useEffect(() => {
    const provided = String(item?.plex_watch_url || "").trim();
    if (provided) {
      setPlexHref(provided);
      return undefined;
    }
    if (!showWatch) {
      setPlexHref("");
      return undefined;
    }
    let cancelled = false;
    loadPlexMachineId().then((machineId) => {
      if (cancelled) return;
      setPlexHref(plexWatchUrl(item.rating_key, machineId));
    });
    return () => {
      cancelled = true;
    };
  }, [item?.plex_watch_url, item?.rating_key, showWatch]);

  useEffect(() => {
    if (!trailerOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setTrailerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [trailerOpen]);

  async function handleTrailer(event) {
    event.preventDefault();
    event.stopPropagation();
    if (trailerKey) {
      setTrailerOpen(true);
      return;
    }
    if (!item?.media_type || !(item.tmdb_id || item.rating_key)) return;
    setTrailerLoading(true);
    try {
      const id = item.tmdb_id || item.rating_key;
      const idType = item.tmdb_id ? "tmdb" : "rating_key";
      const detail = await api(
        `/title/${item.media_type}/${id}?id_type=${encodeURIComponent(idType)}&enrich=1`,
      );
      const key = String(detail?.trailer_youtube_key || "").trim();
      if (key) {
        setTrailerKey(key);
        setTrailerOpen(true);
      }
    } catch {
      // Trailer unavailable — user can open title detail.
    } finally {
      setTrailerLoading(false);
    }
  }

  const media = item.poster_url ? (
    <img src={item.poster_url} alt="" loading="lazy" />
  ) : (
    <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
  );

  const showHoverActions = Boolean(
    (showWatch && plexHref) || item?.tmdb_id || item?.rating_key || (showRecommend && onRecommend),
  );

  const body = (
    <>
      <div className="explore-poster">{media}</div>
      <h3>{item.title || "Untitled"}</h3>
      {item.year ? <p className="explore-card-meta">{item.year}</p> : null}
      {meta ? <p className="explore-card-meta explore-card-context">{meta}</p> : null}
    </>
  );

  return (
    <article
      className={`explore-cinema-card${hovered ? " is-hovered" : ""}`}
      data-testid={testId}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {path ? (
        <Link to={path} className="explore-cinema-card-link">
          {body}
        </Link>
      ) : (
        <div className="explore-cinema-card-link">{body}</div>
      )}

      {showHoverActions ? (
        <div className="explore-card-hover-actions" data-testid="explore-card-hover-actions">
          {showWatch && plexHref ? (
            <a
              href={plexHref}
              className="explore-hover-btn"
              data-testid="explore-watch-plex"
              target="_blank"
              rel="noopener noreferrer"
              onClick={(event) => event.stopPropagation()}
            >
              Watch
            </a>
          ) : null}
          {item?.tmdb_id || item?.rating_key ? (
            <button
              type="button"
              className="explore-hover-btn"
              data-testid="explore-view-trailer"
              disabled={trailerLoading}
              onClick={handleTrailer}
            >
              {trailerLoading ? "…" : "Trailer"}
            </button>
          ) : null}
          {showRecommend && onRecommend ? (
            <button
              type="button"
              className="explore-hover-btn"
              data-testid="explore-recommend"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onRecommend(item);
              }}
            >
              Recommend
            </button>
          ) : null}
        </div>
      ) : null}

      {onSeed && item.id != null ? (
        <button
          type="button"
          className="ghost explore-seed-btn"
          data-testid="explore-seed-btn"
          onClick={() => onSeed(item)}
        >
          {seedLabel}
        </button>
      ) : null}

      {trailerOpen && trailerKey ? (
        <div
          className="trailer-modal-backdrop"
          data-testid="explore-trailer-modal"
          onClick={() => setTrailerOpen(false)}
          role="presentation"
        >
          <div
            className="trailer-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`${item.title || "Title"} trailer`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="trailer-modal-header">
              <h2>{item.title || "Trailer"}</h2>
              <button
                type="button"
                className="ghost"
                data-testid="close-explore-trailer"
                onClick={() => setTrailerOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="trailer-modal-frame">
              <iframe
                title={`${item.title || "Title"} trailer`}
                src={`https://www.youtube.com/embed/${encodeURIComponent(trailerKey)}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}
