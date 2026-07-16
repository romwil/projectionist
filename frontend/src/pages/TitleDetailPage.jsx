import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, getFeatures } from "../api/client";
import RecommendModal from "../components/RecommendModal";
import { canWatchOnPlex, plexWatchUrl } from "../lib/titleLinks.js";

export default function TitleDetailPage() {
  const { mediaType, itemId } = useParams();
  const [searchParams] = useSearchParams();
  const idType = searchParams.get("id_type") || "tmdb";
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [multiUserEnabled, setMultiUserEnabled] = useState(false);

  useEffect(() => {
    setDetail(null);
    setError("");
    setTrailerOpen(false);
    setRecommendOpen(false);
    const query = idType && idType !== "tmdb" ? `?id_type=${encodeURIComponent(idType)}` : "";
    api(`/title/${mediaType}/${itemId}${query}`)
      .then(setDetail)
      .catch((err) => setError(err.message));
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
  if (!detail) return <p>Loading…</p>;

  const trailerKey = String(detail.trailer_youtube_key || "").trim();
  const plexHref =
    String(detail.plex_watch_url || "").trim() ||
    (canWatchOnPlex(detail) ? plexWatchUrl(detail.rating_key, detail.plex_machine_id || "") : "");

  return (
    <div className="title-page" data-testid="title-detail-page">
      <Link to="/">← Back to chat</Link>
      <div className="title-hero" style={{ backgroundImage: detail.backdrop_url ? `url(${detail.backdrop_url})` : undefined }}>
        <div className="title-hero-content">
          {detail.poster_url ? <img src={detail.poster_url} alt="" className="hero-poster" /> : null}
          <div>
            <p className="eyebrow">{detail.media_type === "movie" ? "Movie" : "TV Show"}</p>
            <h1>
              {detail.title}
              {detail.year ? ` (${detail.year})` : ""}
            </h1>
            {detail.rating ? <p>TMDB {detail.rating.toFixed(1)}</p> : null}
            {detail.in_library ? <span className="badge">In your library</span> : null}
            <p>{detail.overview}</p>
            {detail.genres?.length ? <p>{detail.genres.join(" · ")}</p> : null}
            {detail.purge_reason ? <p className="purge-note">Purge consideration: {detail.purge_reason}</p> : null}
            <div className="title-detail-actions">
              {trailerKey ? (
                <button
                  type="button"
                  data-testid="watch-trailer-button"
                  onClick={() => setTrailerOpen(true)}
                >
                  Watch trailer
                </button>
              ) : null}
              {plexHref ? (
                <a
                  href={plexHref}
                  className="btn-link title-detail-plex-link"
                  data-testid="watch-on-plex-button"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Watch on Plex
                </a>
              ) : null}
              {multiUserEnabled ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid="recommend-title-button"
                  onClick={() => setRecommendOpen(true)}
                >
                  Recommend to…
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>

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
