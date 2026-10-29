import type {JsonObject, JsParam} from "../api/types";
const CONFIDENCE_LABELS: Record<string, any> = {
  certain: "Certain",
  likely: "Likely",
  plex_event_only: "Plex played event",
};

export function completionConfidenceLabel(confidence: JsParam) {
  return CONFIDENCE_LABELS[String(confidence || "")] || "Unknown evidence";
}

function plural(count: unknown, singular: JsParam, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function normalizeWatchSummary(raw: unknown = {}) {
  const confidence = {
    certain: Number((raw as JsParam)?.completion_confidence?.certain || 0),
    likely: Number((raw as JsParam)?.completion_confidence?.likely || 0),
    plex_event_only: Number((raw as JsParam)?.completion_confidence?.plex_event_only || 0),
  };
  const coverage = String((raw as JsParam)?.tracker_coverage || "none");
  const plexCount = Number((raw as JsParam)?.plex_played_event_count || 0);
  return {
    ...(raw && typeof raw === "object" ? (raw as JsParam) : {}),
    tracker_coverage: coverage,
    tracked_completions: Number((raw as JsParam)?.tracked_completions || 0),
    logical_viewings: Number((raw as JsParam)?.logical_viewings || 0),
    sittings_observed: Number((raw as JsParam)?.sittings_observed || 0),
    completion_confidence: confidence,
    timeline: Array.isArray((raw as JsParam)?.completion_timeline)
      ? (raw as JsParam).completion_timeline
      : Array.isArray((raw as JsParam)?.recent_activity)
        ? (raw as JsParam).recent_activity
        : [],
    hasCoverage: coverage !== "none",
    fallbackLabel:
      plexCount > 0
        ? `Plex marked played ${plural(plexCount, "time")}`
        : "None",
  };
}

/** Plain watched fact. One viewing is "Watched"; another pass says how many times. */
export function watchedTimesLabel(count: unknown) {
  const n = Number(count || 0);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n === 1) return "Watched";
  return `Watched ${n} times`;
}

/** Sittings are evidence observations, not a second play-count. */
export function sittingsObservedLabel(count: unknown) {
  const n = Number(count || 0);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n === 1 ? "1 sitting observed" : `${n} sittings observed`;
}

export function episodeHistorySummary(summary: JsParam = {}) {
  const unique = Number(summary.unique_episodes_completed || 0);
  const repeats = Number(summary.repeat_episode_completions || 0);
  const parts: JsParam[] = [];
  if (unique > 0) {
    parts.push(`${unique} ${unique === 1 ? "episode" : "episodes"} watched`);
  } else {
    const total = watchedTimesLabel(summary.total_episode_completions);
    if (total) parts.push(total);
  }
  if (repeats > 0) {
    parts.push(repeats === 1 ? "1 watched again" : `${repeats} watched again`);
  }
  return parts.join(" · ");
}

export function trackedCompletionCardLabel(summary: JsParam) {
  const normalized = summary?.hasCoverage == null ? normalizeWatchSummary(summary) : summary;
  if (!normalized.hasCoverage || normalized.tracked_completions <= 0) return "";
  return watchedTimesLabel(normalized.tracked_completions);
}

export function completionExplanation(completion: JsParam = {}) {
  const confidence = String(completion.confidence || "");
  if (confidence === "certain") {
    return "Projectionist observed progress cross the completion boundary. This does not prove uninterrupted or attentive viewing.";
  }
  if (confidence === "likely") {
    return "Progress and a terminal event strongly support a completion, but the exact threshold crossing was reconstructed.";
  }
  return "Plex emitted a played event without enough progress evidence to reconstruct a viewing. This does not prove uninterrupted viewing.";
}

export function formatTrackedDate(timestamp: number) {
  const value = Number(timestamp || 0);
  if (!value) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
