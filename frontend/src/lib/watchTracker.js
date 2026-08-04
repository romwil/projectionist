const CONFIDENCE_LABELS = {
  certain: "Certain",
  likely: "Likely",
  plex_event_only: "Plex played event",
};

export function completionConfidenceLabel(confidence) {
  return CONFIDENCE_LABELS[String(confidence || "")] || "Unknown evidence";
}

function plural(count, singular, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function normalizeWatchSummary(raw = {}) {
  const confidence = {
    certain: Number(raw?.completion_confidence?.certain || 0),
    likely: Number(raw?.completion_confidence?.likely || 0),
    plex_event_only: Number(raw?.completion_confidence?.plex_event_only || 0),
  };
  const coverage = String(raw?.tracker_coverage || "none");
  const plexCount = Number(raw?.plex_played_event_count || 0);
  return {
    ...raw,
    tracker_coverage: coverage,
    tracked_completions: Number(raw?.tracked_completions || 0),
    logical_viewings: Number(raw?.logical_viewings || 0),
    sittings_observed: Number(raw?.sittings_observed || 0),
    completion_confidence: confidence,
    timeline: Array.isArray(raw?.completion_timeline)
      ? raw.completion_timeline
      : Array.isArray(raw?.recent_activity)
        ? raw.recent_activity
        : [],
    hasCoverage: coverage !== "none",
    fallbackLabel:
      plexCount > 0
        ? `Plex marked played ${plural(plexCount, "time")}`
        : "None",
  };
}

export function trackedCompletionCardLabel(summary) {
  const normalized = summary?.hasCoverage == null ? normalizeWatchSummary(summary) : summary;
  if (!normalized.hasCoverage || normalized.tracked_completions <= 0) return "";
  return plural(normalized.tracked_completions, "tracked completion");
}

export function completionExplanation(completion = {}) {
  const confidence = String(completion.confidence || "");
  if (confidence === "certain") {
    return "Projectionist observed progress cross the completion boundary. This does not prove uninterrupted or attentive viewing.";
  }
  if (confidence === "likely") {
    return "Progress and a terminal event strongly support a completion, but the exact threshold crossing was reconstructed.";
  }
  return "Plex emitted a played event without enough progress evidence to reconstruct a viewing. This does not prove uninterrupted viewing.";
}

export function formatTrackedDate(timestamp) {
  const value = Number(timestamp || 0);
  if (!value) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
