import { useEffect, useState } from "react";
import { getWatchSummary } from "../api/client.js";
import {
  completionConfidenceLabel,
  completionExplanation,
  formatTrackedDate,
  normalizeWatchSummary,
  sittingsObservedLabel,
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

  const watchedLabel = summary ? watchedTimesLabel(summary.tracked_completions) : "";
  const sittingsLabel = summary ? sittingsObservedLabel(summary.sittings_observed) : "";
  const summaryParts = [watchedLabel || (summary?.hasCoverage ? "Not watched yet" : ""), sittingsLabel].filter(Boolean);

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
            {summaryParts.join(" · ")}
          </p>
          {summary.timeline.length ? (
            <ol className="watch-history-timeline">
              {summary.timeline.map((completion: any, index: any) => (
                <li key={`${completion.completed_at_ms || "unknown"}-${index}`}>
                  <span className="watch-history-date">
                    {formatTrackedDate(completion.completed_at_ms)}
                  </span>
                  <span className={`watch-confidence is-${completion.confidence || "unknown"}`}>
                    {completionConfidenceLabel(completion.confidence)}
                  </span>
                  <details>
                    <summary>Why this count?</summary>
                    <p>{completionExplanation(completion)}</p>
                  </details>
                </li>
              ))}
            </ol>
          ) : null}
        </>
      )}
    </section>
  );
}
