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
  onOpenDetail,
  motifWhy = null,
  testId = "explore-title-card",
}) {
  const [hovered, setHovered] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  const [plexHref, setPlexHref] = useState(() => String(item?.plex_watch_url || "").trim());
  const [trailerKey, setTrailerKey] = useState(() => String(item?.trailer_youtube_key || "").trim());
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [trailerLoading, setTrailerLoading] = useState(false);

  const path = titleDetailPath({ ...item, in_library: true });
  const showWatch = canWatchOnPlex(item);

  useEffect(() => {
    setWhyOpen(false);
  }, [item?.id, item?.rating_key, motifWhy?.summary]);

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

  const showCornerActions = Boolean(
    item?.tmdb_id || item?.rating_key || (showRecommend && onRecommend),
  );

  // Play stays centered and always visible for in-library titles (does not share the
  // top-left corner with multi-select checkboxes).
  const playAction =
    showWatch && plexHref ? (
      <a
        href={plexHref}
        className="explore-hover-icon explore-hover-icon-watch is-always-on"
        data-testid="explore-watch-plex"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Watch on Plex"
        title="Watch on Plex"
        onClick={(event) => event.stopPropagation()}
      >
        <span className="material-symbols-outlined" aria-hidden="true">
          play_arrow
        </span>
      </a>
    ) : null;

  const cornerActions = showCornerActions ? (
    <div className="explore-card-hover-actions" data-testid="explore-card-hover-actions">
      {item?.tmdb_id || item?.rating_key ? (
        <button
          type="button"
          className="explore-hover-icon explore-hover-icon-trailer"
          data-testid="explore-view-trailer"
          disabled={trailerLoading}
          aria-label={trailerLoading ? "Loading trailer" : "Watch trailer"}
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
          data-testid="explore-recommend"
          aria-label="Recommend"
          title="Recommend"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onRecommend(item);
          }}
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            recommend
          </span>
        </button>
      ) : null}
    </div>
  ) : null;

  const titleBlock = (
    <>
      <h3>{item.title || "Untitled"}</h3>
      {item.year ? <p className="explore-card-meta">{item.year}</p> : null}
      {meta ? <p className="explore-card-meta explore-card-context">{meta}</p> : null}
    </>
  );

  function handleOpenDetail(event) {
    if (!onOpenDetail) return;
    event.preventDefault();
    onOpenDetail(item, event);
  }

  const posterNode =
    path && onOpenDetail ? (
      <button
        type="button"
        className="explore-poster-link explore-poster-button"
        tabIndex={-1}
        aria-hidden="true"
        onClick={handleOpenDetail}
      >
        {media}
      </button>
    ) : path ? (
      <Link to={path} className="explore-poster-link" tabIndex={-1} aria-hidden="true">
        {media}
      </Link>
    ) : (
      media
    );

  const titleNode =
    path && onOpenDetail ? (
      <button type="button" className="explore-cinema-card-link explore-cinema-card-button" onClick={handleOpenDetail}>
        {titleBlock}
      </button>
    ) : path ? (
      <Link to={path} className="explore-cinema-card-link">
        {titleBlock}
      </Link>
    ) : (
      <div className="explore-cinema-card-link">{titleBlock}</div>
    );

  return (
    <article
      className={`explore-cinema-card${hovered ? " is-hovered" : ""}`}
      data-testid={testId}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="explore-poster">
        {posterNode}
        {playAction}
        {cornerActions}
      </div>
      {titleNode}

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

      {motifWhy ? (
        <div className="explore-motif-why" data-testid="explore-motif-why">
          <button
            type="button"
            className="ghost explore-motif-why-btn"
            data-testid="explore-motif-why-btn"
            aria-expanded={whyOpen}
            onClick={() => setWhyOpen((open) => !open)}
          >
            {whyOpen ? "Hide why" : "Why?"}
          </button>
          {whyOpen ? (
            <div className="explore-motif-why-detail" data-testid="explore-motif-why-detail">
              <p>{motifWhy.summary}</p>
              {motifWhy.matched?.length ? (
                <p className="explore-motif-why-matched">
                  Motifs: {motifWhy.matched.join(" · ")}
                </p>
              ) : null}
              {motifWhy.excerpts?.length ? (
                <ul className="explore-motif-why-excerpts">
                  {motifWhy.excerpts.map((entry) => (
                    <li key={`${entry.motif}-${entry.excerpt}`}>
                      <strong>{entry.motif}</strong>
                      <span>{entry.excerpt}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
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
              <div className="trailer-modal-actions">
                <a
                  className="btn-link ghost"
                  href={`https://www.youtube.com/watch?v=${encodeURIComponent(trailerKey)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open on YouTube
                </a>
                <button
                  type="button"
                  className="ghost"
                  data-testid="close-explore-trailer"
                  onClick={() => setTrailerOpen(false)}
                >
                  Close
                </button>
              </div>
            </div>
            <div className="trailer-modal-frame">
              <iframe
                title={`${item.title || "Title"} trailer`}
                src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(trailerKey)}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
                referrerPolicy="strict-origin-when-cross-origin"
                allowFullScreen
              />
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}
