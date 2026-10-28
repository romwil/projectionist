import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import {
  posterTrailerRequestPath,
  trailerLookupOutcome,
} from "../lib/posterTrailer.js";
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
/** Props for PosterOverlayControls. `any` = API/handler bags until Wave 4 client generics. */
type PosterOverlayControlsProps = {
  item?: any;
  onRecommend?: (...args: any[]) => void;
  showRecommend?: boolean;
  onSeed?: (...args: any[]) => void;
  onTogglePin?: (...args: any[]) => void;
  pinned?: boolean;
  motifWhy?: any;
  testPrefix?: any;
};

export default function PosterOverlayControls({
  item,
  onRecommend,
  showRecommend = false,
  onSeed,
  onTogglePin,
  pinned = false,
  motifWhy,
  testPrefix = "explore",
}: PosterOverlayControlsProps) {
  const location = useLocation();
  const [trailerKey, setTrailerKey] = useState(() => String(item?.trailer_youtube_key || "").trim());
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [trailerLoading, setTrailerLoading] = useState(false);
  const [trailerNotice, setTrailerNotice] = useState("");
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showWatch = canWatchOnPlex(item);
  const playTo = showWatch ? libraryWatchTo(plexPlayRatingKey(item), (location as any)) : null;
  const hasWatchBadge = watchProgressState(item) !== "unwatched";

  useEffect(() => {
    if (!trailerOpen) return undefined;
    const close = (event: any) => {
      if (event.key === "Escape") setTrailerOpen(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [trailerOpen]);

  useEffect(() => {
    return () => {
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    };
  }, []);

  function showTrailerNotice(message: any) {
    setTrailerNotice(message);
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    noticeTimerRef.current = setTimeout(() => setTrailerNotice(""), 2800);
  }

  function applyTrailerOutcome(outcome: any) {
    setTrailerLoading(false);
    if (outcome.key) {
      setTrailerKey(outcome.key);
      setTrailerOpen(true);
      return;
    }
    if (outcome.toast) showTrailerNotice(outcome.toast);
  }

  async function handleTrailer(event: any) {
    event.preventDefault();
    event.stopPropagation();
    if (trailerKey) {
      setTrailerOpen(true);
      return;
    }
    const path = posterTrailerRequestPath(item);
    if (!path) {
      applyTrailerOutcome(trailerLookupOutcome({ detail: null }));
      return;
    }
    setTrailerLoading(true);
    try {
      const detail = await api(path);
      applyTrailerOutcome(trailerLookupOutcome({ detail }));
    } catch (error: unknown) {
      applyTrailerOutcome(trailerLookupOutcome({ error: error as any }));
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
      {trailerNotice && typeof document !== "undefined"
        ? createPortal(
            <div className="menu-action-flash" role="status" aria-live="polite" data-testid={`${testPrefix}-trailer-flash`}>
              {trailerNotice}
            </div>,
            document.body,
          )
        : null}
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
