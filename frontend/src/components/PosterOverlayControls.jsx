import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import {
  canWatchOnPlex,
  libraryWatchTo,
  plexPlayRatingKey,
} from "../lib/titleLinks.js";
import { watchProgressState } from "../lib/watchProgress.js";
import PosterActionMenu from "./PosterActionMenu";
import WatchProgressBadge from "./WatchProgressBadge";

/**
 * Shared interactive title-poster controls. Play deliberately requires a
 * library identity; TMDB-only/discovery cards retain their non-play actions.
 */
export default function PosterOverlayControls({
  item,
  onRecommend,
  showRecommend = false,
  onSeed,
  onTogglePin,
  pinned = false,
  motifWhy,
  testPrefix = "explore",
}) {
  const location = useLocation();
  const [trailerKey, setTrailerKey] = useState(() => String(item?.trailer_youtube_key || "").trim());
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [trailerLoading, setTrailerLoading] = useState(false);
  const showWatch = canWatchOnPlex(item);
  const playTo = showWatch ? libraryWatchTo(plexPlayRatingKey(item), location) : null;
  const hasWatchBadge = watchProgressState(item) !== "unwatched";

  useEffect(() => {
    if (!trailerOpen) return undefined;
    const close = (event) => {
      if (event.key === "Escape") setTrailerOpen(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
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
      const detail = await api(`/title/${item.media_type}/${id}?id_type=${encodeURIComponent(idType)}&enrich=1`);
      const key = String(detail?.trailer_youtube_key || "").trim();
      if (key) {
        setTrailerKey(key);
        setTrailerOpen(true);
      }
    } catch {
      // Trailer unavailable — title detail remains available.
    } finally {
      setTrailerLoading(false);
    }
  }

  const showCornerActions = Boolean(item?.tmdb_id || item?.rating_key || (showRecommend && onRecommend));

  return (
    <>
      <WatchProgressBadge item={item} />
      {showWatch && playTo ? (
        <Link
          to={playTo}
          className="explore-hover-icon explore-hover-icon-watch is-always-on"
          data-testid={`${testPrefix}-watch-plex`}
          aria-label="Play"
          title="Play"
          onClick={(event) => event.stopPropagation()}
        >
          <span className="material-symbols-outlined" aria-hidden="true">play_circle</span>
        </Link>
      ) : null}
      <PosterActionMenu
        item={item}
        onRecommend={onRecommend}
        onSeed={onSeed}
        onTogglePin={onTogglePin}
        pinned={pinned}
        motifWhy={motifWhy}
      />
      {showCornerActions ? (
        <div className="explore-card-hover-actions" data-testid={`${testPrefix}-card-hover-actions`}>
          {item?.tmdb_id || item?.rating_key ? (
            <button
              type="button"
              className="explore-hover-icon explore-hover-icon-trailer"
              data-testid={`${testPrefix}-view-trailer`}
              disabled={trailerLoading}
              aria-label={trailerLoading ? "Loading trailer" : "Trailer"}
              title="Trailer"
              onClick={handleTrailer}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                {trailerLoading ? "progress_activity" : "movie"}
              </span>
            </button>
          ) : null}
          {showRecommend && onRecommend ? (
            <button
              type="button"
              className="explore-hover-icon explore-hover-icon-recommend"
              data-testid={`${testPrefix}-recommend`}
              aria-label="Watch together"
              title="Watch together"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onRecommend(item);
              }}
            >
              <span className="material-symbols-outlined" aria-hidden="true">groups</span>
            </button>
          ) : null}
        </div>
      ) : null}
      {trailerOpen && trailerKey ? (
        <div className="trailer-modal-backdrop" data-testid={`${testPrefix}-trailer-modal`} onClick={() => setTrailerOpen(false)} role="presentation">
          <div className="trailer-modal" role="dialog" aria-modal="true" aria-label={`${item.title || "Title"} trailer`} onClick={(event) => event.stopPropagation()}>
            <div className="trailer-modal-header">
              <h2>{item.title || "Trailer"}</h2>
              <div className="trailer-modal-actions">
                <a className="btn-link ghost" href={`https://www.youtube.com/watch?v=${encodeURIComponent(trailerKey)}`} target="_blank" rel="noopener noreferrer">Open on YouTube</a>
                <button type="button" className="ghost" onClick={() => setTrailerOpen(false)}>Close</button>
              </div>
            </div>
            <div className="trailer-modal-frame">
              <iframe title={`${item.title || "Title"} trailer`} src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(trailerKey)}?autoplay=1&rel=0`} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen" referrerPolicy="strict-origin-when-cross-origin" allowFullScreen />
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
