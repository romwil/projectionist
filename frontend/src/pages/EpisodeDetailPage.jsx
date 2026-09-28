import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { getLibraryEpisode } from "../api/client";
import BackLink from "../components/BackLink";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { formatEpisodeCode } from "../lib/showSeasons.js";
import {
  libraryEpisodePath,
  libraryWatchTo,
  plexWatchUrl,
  titleDetailPath,
} from "../lib/titleLinks.js";

function formatAired(airedAt) {
  const raw = String(airedAt || "").trim();
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw.slice(0, 10);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Plex-like episode detail: still/meta + Play primary + next/prev + back to show.
 */
export default function EpisodeDetailPage() {
  const { ratingKey: rawKey } = useParams();
  const location = useLocation();
  const ratingKey = decodeURIComponent(String(rawKey || "").trim());
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ratingKey) {
      setError("Missing episode.");
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    getLibraryEpisode(ratingKey)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || "Could not load this episode.");
        setPayload(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ratingKey]);

  const episode = payload?.episode;
  const show = payload?.show;
  const code = formatEpisodeCode(episode?.season_number, episode?.episode_number);
  const playTo = episode?.rating_key ? libraryWatchTo(episode.rating_key, location) : null;
  const plexHref = episode?.rating_key
    ? plexWatchUrl(episode.rating_key, "")
    : "";
  const showPath =
    show?.tmdb_id != null
      ? titleDetailPath({ media_type: "show", tmdb_id: show.tmdb_id })
      : show?.rating_key
        ? titleDetailPath({ media_type: "show", rating_key: show.rating_key })
        : null;
  const prevPath = payload?.prev_episode?.rating_key
    ? libraryEpisodePath(payload.prev_episode.rating_key)
    : "";
  const nextPath = payload?.next_episode?.rating_key
    ? libraryEpisodePath(payload.next_episode.rating_key)
    : "";
  const aired = formatAired(episode?.aired_at);

  return (
    <AppShell
      className="title-page title-detail-skinned episode-detail-page"
      testId="episode-detail-page"
      variant="sticky"
      leading={<BackLink fallbackTo={showPath || ROUTES.chat} testId="episode-detail-back" />}
    >
      {loading ? <p className="muted">Opening the episode…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {!loading && !error && episode ? (
        <article className="episode-detail" data-testid="episode-detail">
          <div
            className="episode-detail-stage"
            style={
              show?.poster_url
                ? { backgroundImage: `linear-gradient(180deg, rgba(5,6,8,0.35), rgba(5,6,8,0.92)), url(${show.poster_url})` }
                : undefined
            }
          >
            <div className="episode-detail-stage-veil" aria-hidden="true" />
            <div className="episode-detail-copy">
              {show?.title ? (
                showPath ? (
                  <Link className="episode-detail-show" to={showPath} data-testid="episode-detail-show-link">
                    {show.title}
                  </Link>
                ) : (
                  <p className="episode-detail-show">{show.title}</p>
                )
              ) : null}
              <p className="episode-detail-code">{code}</p>
              <h1 className="episode-detail-title">{episode.title || "Episode"}</h1>
              <div className="episode-detail-meta">
                {aired ? <span>{aired}</span> : null}
                {episode.runtime_minutes ? <span>{episode.runtime_minutes} min</span> : null}
                <span>{episode.unwatched ? "Unwatched" : "Watched"}</span>
              </div>
              <div className="episode-detail-cta" data-testid="episode-detail-cta">
                {playTo ? (
                  <Link to={playTo} className="title-cta title-cta-primary" data-testid="episode-detail-play">
                    <span className="material-symbols-outlined" aria-hidden="true">
                      play_circle
                    </span>
                    Play
                  </Link>
                ) : null}
                {plexHref ? (
                  <a
                    href={plexHref}
                    className="title-cta title-cta-ghost"
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="episode-detail-plex"
                  >
                    Open in Plex
                  </a>
                ) : null}
              </div>
            </div>
          </div>
          <nav className="episode-detail-nav" aria-label="Episode neighbors">
            {prevPath ? (
              <Link className="episode-detail-neighbor" to={prevPath} data-testid="episode-detail-prev">
                <span className="muted">Previous</span>
                <span>
                  {formatEpisodeCode(payload.prev_episode.season_number, payload.prev_episode.episode_number)}{" "}
                  {payload.prev_episode.title}
                </span>
              </Link>
            ) : (
              <span className="episode-detail-neighbor is-empty" />
            )}
            {nextPath ? (
              <Link
                className="episode-detail-neighbor episode-detail-neighbor--next"
                to={nextPath}
                data-testid="episode-detail-next"
              >
                <span className="muted">Next</span>
                <span>
                  {formatEpisodeCode(payload.next_episode.season_number, payload.next_episode.episode_number)}{" "}
                  {payload.next_episode.title}
                </span>
              </Link>
            ) : (
              <span className="episode-detail-neighbor is-empty" />
            )}
          </nav>
        </article>
      ) : null}
    </AppShell>
  );
}
