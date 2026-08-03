import { useEffect, useState } from "react";
import { getWatchSummary } from "../api/client.js";
import {
  completionConfidenceLabel,
  completionExplanation,
  formatTrackedDate,
  normalizeWatchSummary,
  trackedCompletionCardLabel,
} from "../lib/watchTracker.js";

export default function WatchHistoryTimeline({ ratingKey, plexPlayedEventCount = 0 }) {
  const [summary, setSummary] = useState(null);
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
        <>
          <p data-testid="watch-history-fallback">{summary.fallbackLabel}</p>
          <p className="status status-secondary">
            Projectionist has no user-scoped tracker coverage for this title yet, so this is
            the older Plex aggregate—not a playback-session count.
          </p>
        </>
      ) : (
        <>
          <p className="watch-history-summary" data-testid="watch-history-summary">
            {trackedCompletionCardLabel(summary) || "No tracked completions yet"}
            {summary.sittings_observed > 0
              ? ` · ${summary.sittings_observed} evidence observations`
              : ""}
          </p>
          {summary.timeline.length ? (
            <ol className="watch-history-timeline">
              {summary.timeline.map((completion, index) => (
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
          ) : (
            <p className="status status-secondary">
              Evidence exists, but it has not produced a tracked completion.
            </p>
          )}
          <p className="status status-secondary">
            Confidence describes the evidence Projectionist observed; it never proves
            uninterrupted or attentive viewing.
          </p>
        </>
      )}
    </section>
  );
}
