import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, getFeatures } from "../api/client";
import RecommendModal from "../components/RecommendModal";
import { displayRecommendationReason } from "../lib/recommendationReason.js";
import { canWatchOnPlex, plexWatchUrl, titleDetailPath } from "../lib/titleLinks.js";

function decadeLabel(year) {
  if (!year || year < 1000) return null;
  return `${Math.floor(year / 10) * 10}s`;
}

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return null;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function MetaTile({ label, value }) {
  if (!value) return null;
  return (
    <div className="title-meta-tile">
      <span className="title-meta-tile-label">{label}</span>
      <span className="title-meta-tile-value">{value}</span>
    </div>
  );
}

export default function TitleDetailPage() {
  const { mediaType, itemId } = useParams();
  const [searchParams] = useSearchParams();
  const idType = searchParams.get("id_type") || "tmdb";
  const [detail, setDetail] = useState(null);
  const [neighbors, setNeighbors] = useState(null);
  const [error, setError] = useState("");
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);
  const carouselRef = useRef(null);

  useEffect(() => {
    setDetail(null);
    setNeighbors(null);
    setError("");
    setTrailerOpen(false);
    setRecommendOpen(false);
    const query = idType && idType !== "tmdb" ? `?id_type=${encodeURIComponent(idType)}` : "";
    api(`/title/${mediaType}/${itemId}${query}`)
      .then(setDetail)
      .catch((err) => setError(err.message));

    const neighborQuery = new URLSearchParams({ limit: "12" });
    if (idType && idType !== "tmdb") neighborQuery.set("id_type", idType);
    api(`/title/${mediaType}/${itemId}/neighbors?${neighborQuery}`)
      .then((data) => setNeighbors(Array.isArray(data?.items) ? data.items : []))
      .catch(() => setNeighbors([]));
  }, [mediaType, itemId, idType]);

  useEffect(() => {
    getFeatures()
      .then((data) => setMultiUserEnabled(Boolean(data?.features?.multi_user_enabled)))
      .catch(() => setMultiUserEnabled(false));
  }, []);

  useEffect(() => {
    if (!trailerOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setTrailerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [trailerOpen]);

  if (error) return <p className="error">{error}</p>;
  if (!detail) return <p className="title-detail-loading">Loading…</p>;

  const trailerKey = String(detail.trailer_youtube_key || "").trim();
  const plexHref =
    String(detail.plex_watch_url || "").trim() ||
    (canWatchOnPlex(detail) ? plexWatchUrl(detail.rating_key, detail.plex_machine_id || "") : "");
  const whyReason = displayRecommendationReason(detail.recommendation_reason);
  const overviewInsight =
    whyReason ||
    (detail.overview
      ? detail.overview.length > 220
        ? `${detail.overview.slice(0, 220).trim()}…`
        : detail.overview
      : "");
  const showWhy = Boolean(whyReason || overviewInsight);
  const purgeNote = String(detail.purge_reason || "").trim();
  const runtimeLabel = detail.runtime_minutes ? `${detail.runtime_minutes} mins` : null;
  const genreLabel = detail.genres?.length ? detail.genres.slice(0, 2).join(" · ") : null;
  const directorLabel = detail.directors?.length ? detail.directors[0] : null;
  const sizeLabel = formatFileSize(detail.file_size_bytes);
  const showNeighbors = Array.isArray(neighbors) && neighbors.length > 0;

  function scrollCarousel(dir) {
    const node = carouselRef.current;
    if (!node) return;
    node.scrollBy({ left: dir * 320, behavior: "smooth" });
  }

  return (
    <div className="title-page title-detail-skinned" data-testid="title-detail-page">
      <header className="title-detail-sticky-header">
        <Link to="/" className="title-detail-back">
          ← Back to chat
        </Link>
        <span className="title-detail-sticky-label">
          {detail.media_type === "movie" ? "Movie" : "TV Show"}
        </span>
      </header>

      <section
        className="title-detail-hero"
        style={detail.backdrop_url ? { "--title-backdrop": `url(${detail.backdrop_url})` } : undefined}
        data-testid="title-detail-hero"
      >
        <div className="title-detail-hero-scrim" aria-hidden="true" />
        <div className="title-detail-hero-inner">
          <div className="title-detail-chips">
            {detail.year ? <span className="title-chip">{detail.year}</span> : null}
            {runtimeLabel ? (
              <span className="title-chip title-chip-accent">
                <span className="material-symbols-outlined" aria-hidden="true">
                  schedule
                </span>
                {runtimeLabel}
              </span>
            ) : null}
            {detail.in_library ? <span className="title-chip title-chip-success">In library</span> : null}
            {detail.rating ? (
              <span className="title-chip">TMDB {Number(detail.rating).toFixed(1)}</span>
            ) : null}
          </div>
          <h1 className="title-detail-headline">{detail.title}</h1>
          <div className="title-detail-cta-row">
            {plexHref ? (
              <a
                href={plexHref}
                className="title-cta title-cta-primary"
                data-testid="watch-on-plex-button"
                target="_blank"
                rel="noopener noreferrer"
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  play_circle
                </span>
                Watch on Plex
              </a>
            ) : null}
            {trailerKey ? (
              <button
                type="button"
                className="title-cta title-cta-ghost"
                data-testid="watch-trailer-button"
                onClick={() => setTrailerOpen(true)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  play_arrow
                </span>
                Trailer
              </button>
            ) : null}
            {multiUserEnabled ? (
              <button
                type="button"
                className="title-cta title-cta-icon"
                data-testid="recommend-title-button"
                aria-label="Recommend to…"
                onClick={() => setRecommendOpen(true)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  person_add
                </span>
              </button>
            ) : null}
          </div>
        </div>
      </section>

      <section className="title-detail-grid">
        <div className="title-detail-main">
          {detail.overview ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Synopsis</h2>
              <p className="title-detail-synopsis">{detail.overview}</p>
            </div>
          ) : null}

          {showWhy ? (
            <div className="title-why-card" data-testid="title-why-card">
              <h2 className="title-why-heading">Why this?</h2>
              <p className="title-why-body">{overviewInsight}</p>
              {whyReason ? (
                <p className="title-why-badge">
                  <span className="material-symbols-outlined" aria-hidden="true">
                    auto_awesome
                  </span>
                  Curator note
                </p>
              ) : null}
            </div>
          ) : null}

          {purgeNote ? (
            <aside className="title-purge-callout" data-testid="title-purge-callout">
              <span className="material-symbols-outlined" aria-hidden="true">
                warning
              </span>
              <div>
                <h3>Purge notes</h3>
                <p>{purgeNote}</p>
              </div>
            </aside>
          ) : null}
        </div>

        <aside className="title-detail-side">
          <div className="title-meta-grid">
            <MetaTile label="Decade" value={decadeLabel(detail.year)} />
            <MetaTile label="Director" value={directorLabel} />
            <MetaTile label="Genre" value={genreLabel} />
            <MetaTile label="Size" value={sizeLabel} />
            <MetaTile
              label="Views"
              value={detail.view_count > 0 ? String(detail.view_count) : null}
            />
            <MetaTile
              label="Type"
              value={detail.media_type === "movie" ? "Movie" : "TV Show"}
            />
          </div>

          {detail.keywords?.length ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Tags</h2>
              <div className="title-tag-list">
                {detail.keywords.slice(0, 8).map((tag) => (
                  <span key={tag} className="title-tag">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {detail.cast?.length ? (
            <div className="title-detail-section">
              <h2 className="title-detail-section-label">Cast</h2>
              <ul className="title-cast-list">
                {detail.cast.slice(0, 6).map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </section>

      {showNeighbors ? (
        <section className="title-neighbors" data-testid="title-neighbors">
          <div className="title-neighbors-header">
            <h2>More Like This</h2>
            <div className="title-neighbors-controls">
              <button
                type="button"
                className="ghost title-neighbors-nav"
                aria-label="Scroll left"
                onClick={() => scrollCarousel(-1)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  chevron_left
                </span>
              </button>
              <button
                type="button"
                className="ghost title-neighbors-nav"
                aria-label="Scroll right"
                onClick={() => scrollCarousel(1)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  chevron_right
                </span>
              </button>
            </div>
          </div>
          <div className="title-neighbors-track" ref={carouselRef}>
            {neighbors.map((item) => {
              const path = titleDetailPath(item);
              const card = (
                <>
                  <div className="title-neighbor-poster">
                    {item.poster_url ? (
                      <img src={item.poster_url} alt="" loading="lazy" />
                    ) : (
                      <div className="poster-fallback">{item.title?.slice(0, 1) || "?"}</div>
                    )}
                  </div>
                  <h3>{item.title}</h3>
                  {item.year ? <p className="title-neighbor-year">{item.year}</p> : null}
                </>
              );
              return path ? (
                <Link key={`${item.media_type}-${item.tmdb_id || item.rating_key || item.title}`} to={path} className="title-neighbor-card">
                  {card}
                </Link>
              ) : (
                <div key={`${item.media_type}-${item.title}`} className="title-neighbor-card">
                  {card}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {trailerOpen && trailerKey ? (
        <div
          className="trailer-modal-backdrop"
          data-testid="trailer-modal"
          onClick={() => setTrailerOpen(false)}
        >
          <div
            className="trailer-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Trailer for ${detail.title}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="trailer-modal-header">
              <h2>Trailer</h2>
              <button
                type="button"
                className="ghost"
                data-testid="close-trailer-modal"
                onClick={() => setTrailerOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="trailer-modal-frame">
              <iframe
                title={`${detail.title} trailer`}
                src={`https://www.youtube.com/embed/${encodeURIComponent(trailerKey)}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>
        </div>
      ) : null}

      <RecommendModal
        item={detail}
        open={recommendOpen}
        onClose={() => setRecommendOpen(false)}
      />
    </div>
  );
}
