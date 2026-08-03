import { useCallback, useEffect, useState } from "react";
import { getShowSeasons, getShowWatchSummary, removeTvScope } from "../api/client";
import { canOwnerDeleteLibraryTitle } from "../lib/bulkLibraryDelete.js";
import {
  formatEpisodeCode,
  formatSeasonLabel,
  formatShowBytes,
  normalizeShowSeasonsPayload,
  showSeasonsSummaryLine,
} from "../lib/showSeasons.js";
import {
  completionConfidenceLabel,
  formatTrackedDate,
  normalizeWatchSummary,
} from "../lib/watchTracker.js";
import RemovalSummaryDialog from "./RemovalSummaryDialog.jsx";
import ScopedTvRemoveDialog from "./ScopedTvRemoveDialog.jsx";

/**
 * Seasons / episodes browser for in-library TV shows on title detail.
 */
export default function ShowSeasonsPanel({
  detail,
  userRole = "owner",
  multiUserEnabled = true,
  compact = false,
  onShowDelete,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState("");
  const [removalSummary, setRemovalSummary] = useState(null);
  const [watchSummary, setWatchSummary] = useState(null);

  const showId = detail?.library_item_id ?? null;
  const tmdbId = detail?.tmdb_id ?? null;
  const tvdbId = detail?.tvdb_id ?? null;
  const inLibrary = Boolean(detail?.in_library);
  const canDelete = canOwnerDeleteLibraryTitle(detail, {
    role: userRole,
    multiUserEnabled,
  });

  const load = useCallback(async () => {
    if (!inLibrary || detail?.media_type !== "show") {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await getShowSeasons({
        showId,
        tmdbId: showId == null ? tmdbId : null,
        tvdbId: showId == null && tmdbId == null ? tvdbId : null,
      });
      setData(normalizeShowSeasonsPayload(payload));
    } catch (err) {
      setError(err?.message || "Could not load seasons.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [inLibrary, detail?.media_type, showId, tmdbId, tvdbId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const ratingKey = String(detail?.rating_key || "").trim();
    if (!inLibrary || detail?.media_type !== "show" || !ratingKey) {
      return undefined;
    }
    let cancelled = false;
    getShowWatchSummary(ratingKey)
      .then((payload) => {
        if (!cancelled) setWatchSummary(normalizeWatchSummary(payload));
      })
      .catch(() => {
        if (!cancelled) setWatchSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [detail?.media_type, detail?.rating_key, inLibrary]);

  if (!inLibrary || detail?.media_type !== "show") return null;

  async function handleConfirmRemove() {
    if (!pending) return;
    setRemoving(true);
    setRemoveError("");
    try {
      const body =
        pending.scope === "season"
          ? {
              scope: "season",
              show_id: data?.show_id ?? showId,
              tmdb_id: tmdbId,
              season_number: pending.season_number,
            }
          : {
              scope: "episode",
              show_id: data?.show_id ?? showId,
              tmdb_id: tmdbId,
              episode_rating_key: pending.episode_rating_key,
            };
      const result = await removeTvScope(body);
      setPending(null);
      setRemovalSummary(result);
      await load();
    } catch (err) {
      setRemoveError(err?.message || "Could not remove from disk.");
    } finally {
      setRemoving(false);
    }
  }

  const summary = data ? showSeasonsSummaryLine(data) : "";
  const episodesByRatingKey = new Map(
    (data?.seasons || []).flatMap((season) =>
      (season.episodes || []).map((episode) => [String(episode.rating_key || ""), episode]),
    ),
  );
  const episodeActivityLabel = (activity) => {
    const episode = episodesByRatingKey.get(String(activity?.rating_key || ""));
    if (!episode) return "";
    return `${formatEpisodeCode(episode.season_number, episode.episode_number)} · ${episode.title} · `;
  };

  return (
    <section
      className={`title-detail-section show-seasons-panel${compact ? " is-compact" : ""}`}
      data-testid="show-seasons-panel"
    >
      <div className="show-seasons-head">
        <h2 className="title-detail-section-label">Seasons &amp; episodes</h2>
        {canDelete && typeof onShowDelete === "function" ? (
          <button
            type="button"
            className="ghost show-seasons-show-delete"
            data-testid="show-seasons-remove-show"
            onClick={onShowDelete}
          >
            Remove show
          </button>
        ) : null}
      </div>

      {watchSummary?.hasCoverage ? (
        <div className="show-watch-summary" data-testid="show-watch-summary">
          <h3>Your episode history</h3>
          <p>
            {watchSummary.unique_episodes_completed} episodes completed ·{" "}
            {watchSummary.total_episode_completions} tracked episode completions
            {watchSummary.repeat_episode_completions
              ? ` · ${watchSummary.repeat_episode_completions} repeat episode completions`
              : ""}
          </p>
          {watchSummary.timeline.length ? (
            <ul aria-label="Recent episode completion activity">
              {watchSummary.timeline.slice(0, 5).map((activity, index) => (
                <li key={`${activity.rating_key}-${activity.completed_at_ms}-${index}`}>
                  {episodeActivityLabel(activity)}
                  {formatTrackedDate(activity.completed_at_ms)} ·{" "}
                  {completionConfidenceLabel(activity.confidence)}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="status status-secondary">
            Shows stay episode-first: Projectionist never turns these into “show watched N
            times.”
          </p>
        </div>
      ) : null}

      {loading ? (
        <p className="status status-secondary">Loading seasons…</p>
      ) : error ? (
        <p className="dash-panel-error" role="alert">
          {error}
        </p>
      ) : !data || data.total_episodes === 0 ? (
        <p className="status status-secondary" data-testid="show-seasons-empty">
          Episode list not synced yet — run a library sync to pull seasons from Plex.
        </p>
      ) : (
        <>
          <p className="show-seasons-summary" data-testid="show-seasons-summary">
            {summary}
            {data.truncated ? " · list truncated" : ""}
          </p>
          <div className="show-seasons-list">
            {data.seasons.map((season) => {
              const seasonKey =
                season.season_number == null ? "specials" : String(season.season_number);
              const sizeLabel = formatShowBytes(season.file_size_bytes);
              return (
                <details
                  key={seasonKey}
                  className="show-season-details"
                  data-testid={`show-season-${seasonKey}`}
                  open={data.seasons.length === 1}
                >
                  <summary className="show-season-summary-row">
                    <span className="show-season-title">
                      {formatSeasonLabel(season.season_number)}
                    </span>
                    <span className="show-season-meta">
                      {season.episode_count} ep
                      {season.watched_count
                        ? ` · ${season.watched_count} watched`
                        : ""}
                      {sizeLabel ? ` · ${sizeLabel}` : ""}
                    </span>
                    {canDelete && season.season_number != null ? (
                      <button
                        type="button"
                        className="ghost show-season-remove"
                        data-testid={`show-season-remove-${seasonKey}`}
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          setRemoveError("");
                          setPending({
                            scope: "season",
                            season_number: season.season_number,
                            label: `${data.show_title} · ${formatSeasonLabel(season.season_number)}`,
                          });
                        }}
                      >
                        Remove
                      </button>
                    ) : null}
                  </summary>
                  <ul className="show-episode-list">
                    {season.episodes.map((ep) => {
                      const epSize = formatShowBytes(ep.file_size);
                      const tracked =
                        watchSummary?.episode_completions?.[String(ep.rating_key || "")] || null;
                      return (
                        <li
                          key={ep.rating_key || `${ep.season_number}-${ep.episode_number}`}
                          className="show-episode-row"
                          data-testid="show-episode-row"
                        >
                          <div className="show-episode-main">
                            <span className="show-episode-code">
                              {formatEpisodeCode(ep.season_number, ep.episode_number)}
                            </span>
                            <span className="show-episode-title">{ep.title}</span>
                          </div>
                          <div className="show-episode-meta">
                            {ep.runtime_minutes ? (
                              <span>{ep.runtime_minutes}m</span>
                            ) : null}
                            {epSize ? <span>{epSize}</span> : null}
                            <span>{ep.unwatched ? "Unwatched" : "Watched"}</span>
                            {tracked?.tracked_completions > 0 ? (
                              <span className="watch-confidence" data-testid="episode-tracked-count">
                                {tracked.tracked_completions} tracked{" "}
                                {tracked.tracked_completions === 1
                                  ? "completion"
                                  : "completions"}
                              </span>
                            ) : null}
                            {canDelete && ep.rating_key ? (
                              <button
                                type="button"
                                className="ghost show-episode-remove"
                                data-testid={`show-episode-remove-${ep.rating_key}`}
                                onClick={() => {
                                  setRemoveError("");
                                  setPending({
                                    scope: "episode",
                                    episode_rating_key: ep.rating_key,
                                    label: `${data.show_title} · ${formatEpisodeCode(
                                      ep.season_number,
                                      ep.episode_number,
                                    )} · ${ep.title}`,
                                  });
                                }}
                              >
                                Remove
                              </button>
                            ) : null}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </details>
              );
            })}
          </div>
        </>
      )}

      <ScopedTvRemoveDialog
        open={Boolean(pending)}
        scope={pending?.scope || "episode"}
        label={pending?.label || ""}
        loading={removing}
        error={removeError}
        onCancel={() => {
          if (removing) return;
          setPending(null);
          setRemoveError("");
        }}
        onConfirm={handleConfirmRemove}
      />

      <RemovalSummaryDialog
        open={Boolean(removalSummary)}
        result={removalSummary}
        onClose={() => setRemovalSummary(null)}
      />
    </section>
  );
}
