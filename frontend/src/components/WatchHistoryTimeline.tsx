import { useEffect, useState } from "react";
import { getWatchSummary } from "../api/client.js";
import {
  formatTrackedDate,
  normalizeWatchSummary,
  watchedTimesLabel,
} from "../lib/watchTracker.js";

/** Props for WatchHistoryTimeline. `any` = API/handler bags until Wave 4 client generics. */
type WatchHistoryTimelineProps = {
  ratingKey?: any;
  plexPlayedEventCount?: number;
};

export default function WatchHistoryTimeline({ ratingKey, plexPlayedEventCount = 0 }: WatchHistoryTimelineProps) {
  const [summary, setSummary] = useState<any | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ratingKey) return undefined;
    let cancelled = false;
    getWatchSummary(ratingKey)
      .then((payload) => {
        if (!cancelled) {
          setError("");
          setSummary(
            normalizeWatchSummary({
              ...payload,
              plex_played_event_count: plexPlayedEventCount,
            }),
          );
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Watch history is unavailable.");
      });
    return () => {
      cancelled = true;
    };
  }, [ratingKey, plexPlayedEventCount]);

  if (!ratingKey) return null;

  return (
    <section className="title-detail-section watch-history" data-testid="watch-history">
      <h2 className="title-detail-section-label">Your watch history</h2>
      {error ? (
        <p className="status status-secondary">{error}</p>
      ) : !summary ? (
        <p className="status status-secondary">Loading your watch evidence…</p>
      ) : !summary.hasCoverage ? (
        <p data-testid="watch-history-fallback">{summary.fallbackLabel}</p>
      ) : (
        <>
          <p className="watch-history-summary" data-testid="watch-history-summary">
            {watchedTimesLabel(summary.tracked_completions) || "Not watched yet"}
          </p>
          {summary.timeline.length ? (
            <ol className="watch-history-timeline">
              {summary.timeline.map((completion: any, index: any) => (
                <li key={`${completion.completed_at_ms || "unknown"}-${index}`}>
                  <span className="watch-history-date">
                    {formatTrackedDate(completion.completed_at_ms)}
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
        </>
      )}
    </section>
  );
}
