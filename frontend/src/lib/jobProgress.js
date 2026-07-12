/** Human-friendly job progress labels for Config + StatusDock. */

const FRIENDLY_PROGRESS = {
  queued: "Waiting to start…",
  preparing: "Connecting to Plex…",
  movies: "Scanning Plex movies…",
  tv: "Scanning Plex TV shows…",
  scanning_plex: "Scanning Plex library…",
  enriching: "Enriching metadata…",
  indexing: "Building search indexes…",
  facets: "Building search facets…",
  fts: "Building search index…",
  episodes: "Syncing TV episodes…",
  finishing: "Finishing up…",
  embeddings: "Building recommendations…",
  completed: "Done",
  done: "Done",
  library_sync: "Library sync",
};

const PHASE_LABELS = {
  queued: "Waiting",
  preparing: "Preparing",
  movies: "Scanning movies",
  tv: "Scanning TV",
  enriching: "Enriching metadata",
  indexing: "Building indexes",
  facets: "Building indexes",
  fts: "Building indexes",
  episodes: "Syncing episodes",
  finishing: "Finishing",
  embeddings: "Finishing",
  completed: "Done",
  done: "Done",
};

const SNAKE_KEY = /^[a-z][a-z0-9_]*$/;

export function phaseLabel(phase = "", fallbackLabel = "") {
  if (fallbackLabel && !SNAKE_KEY.test(String(fallbackLabel).trim())) {
    return fallbackLabel;
  }
  const key = String(phase || "").trim().toLowerCase();
  if (PHASE_LABELS[key]) return PHASE_LABELS[key];
  if (key && SNAKE_KEY.test(key)) {
    return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  }
  return "Working";
}

/**
 * Map internal progress keys / snake_case to hoster-friendly copy.
 * Prefer an already-friendly message from the API when present.
 */
export function friendlyProgressMessage(message = "", phase = "", jobType = "") {
  const raw = String(message || "").trim();
  const phaseKey = String(phase || "").trim().toLowerCase();
  const typeKey = String(jobType || "").trim().toLowerCase();

  if (raw && FRIENDLY_PROGRESS[raw]) return FRIENDLY_PROGRESS[raw];
  if (raw && !SNAKE_KEY.test(raw)) return raw;
  if (phaseKey && FRIENDLY_PROGRESS[phaseKey]) return FRIENDLY_PROGRESS[phaseKey];
  if (raw && SNAKE_KEY.test(raw)) {
    return `${raw.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}…`;
  }
  if (typeKey && FRIENDLY_PROGRESS[typeKey]) return FRIENDLY_PROGRESS[typeKey];
  if (typeKey && SNAKE_KEY.test(typeKey)) return typeKey.replace(/_/g, " ");
  return "Working…";
}

/** Clamp displayed percent; never show 100% for an in-progress job. */
export function displayJobPercent(job) {
  const status = job?.status;
  if (status === "completed" || status === "done") return 100;
  if (status === "failed") return null;
  const percent = job?.progress?.percent;
  if (typeof percent !== "number" || Number.isNaN(percent)) return null;
  if (status === "running" || status === "queued") {
    return Math.min(Math.max(Math.round(percent), 0), 99);
  }
  return Math.min(Math.max(Math.round(percent), 0), 100);
}

export function formatCountHint(progress = {}) {
  const current = Number(progress.current);
  const total = Number(progress.total);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 1) return "";
  if (current <= 0) return "";
  if (current < total) return `${current} of ~${total}`;
  return `${total} items`;
}

/** Compact one-line status for StatusDock / alerts. */
export function formatSyncJobStatus(job) {
  if (!job) return null;
  if (job.status === "failed") {
    const err = String(job.error || "")
      .split("\n")
      .map((line) => line.trim())
      .find(Boolean);
    if (!err || /traceback/i.test(err)) return "Sync failed. Check Config and try again.";
    const cleaned = err.length > 160 ? `${err.slice(0, 157)}…` : err;
    return `Sync failed: ${cleaned}`;
  }
  if (job.status === "completed" || job.status === "done") {
    return "Last sync completed.";
  }
  const progress = job.progress || {};
  const label = phaseLabel(progress.phase, progress.label);
  const message = friendlyProgressMessage(progress.message, progress.phase, job.job_type);
  const percent = displayJobPercent(job);
  const count = formatCountHint(progress);
  const parts = [label];
  if (message && message !== label && !message.toLowerCase().startsWith(label.toLowerCase())) {
    parts.push(message);
  } else if (message) {
    parts[0] = message;
  }
  let line = parts.filter(Boolean).join(" — ");
  if (count && !line.includes(String(progress.current))) {
    line = `${line} · ${count}`;
  }
  if (typeof percent === "number" && percent > 0) {
    line = `${line} (${percent}%)`;
  }
  return line;
}

/** Structured view model for the Config library-sync card. */
export function formatSyncJobDetails(job, libraryStats = null) {
  if (!job) return null;
  if (job.status === "failed") {
    return {
      state: "failed",
      headline: "Sync failed",
      detail: formatSyncJobStatus(job).replace(/^Sync failed:\s*/, "") || "Check Config and try again.",
      percent: null,
      countHint: "",
    };
  }
  if (job.status === "completed" || job.status === "done") {
    const movies = libraryStats?.movies;
    const shows = libraryStats?.shows;
    const counts =
      typeof movies === "number" && typeof shows === "number"
        ? ` · ${movies} movies · ${shows} shows`
        : "";
    return {
      state: "completed",
      headline: `Last synced just now${counts}`,
      detail: "",
      percent: 100,
      countHint: "",
    };
  }
  const progress = job.progress || {};
  const percent = displayJobPercent(job);
  return {
    state: "running",
    headline: phaseLabel(progress.phase, progress.label),
    detail: friendlyProgressMessage(progress.message, progress.phase, job.job_type),
    percent,
    countHint: formatCountHint(progress),
  };
}

/**
 * Extract Unix seconds from sync_state `last_sync` values.
 * Accepts a bare number/string, or JSON with timestamp/finished_at/etc.
 */
export function parseLastSyncTimestamp(lastSync) {
  if (lastSync == null || lastSync === "") return null;
  try {
    if (typeof lastSync === "number") {
      return Number.isFinite(lastSync) ? lastSync : null;
    }
    if (typeof lastSync === "string") {
      const trimmed = lastSync.trim();
      if (!trimmed) return null;
      if (/^\d+(\.\d+)?$/.test(trimmed)) {
        const n = Number(trimmed);
        return Number.isFinite(n) ? n : null;
      }
      return parseLastSyncTimestamp(JSON.parse(trimmed));
    }
    if (typeof lastSync === "object") {
      const raw =
        lastSync.timestamp ??
        lastSync.finished_at ??
        lastSync.started_at ??
        lastSync.updated_at;
      if (raw == null || raw === "") return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }
  } catch {
    return null;
  }
  return null;
}

export function formatLastSyncRelative(lastSync) {
  if (lastSync == null || lastSync === "") return "Never synced";
  const timestamp = parseLastSyncTimestamp(lastSync);
  if (timestamp == null) return "Unknown";
  const ms = Number(timestamp) * 1000;
  if (!Number.isFinite(ms) || ms <= 0) return "Unknown";
  const deltaSec = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (deltaSec < 45) return "just now";
  if (deltaSec < 3600) return `${Math.round(deltaSec / 60)} min ago`;
  if (deltaSec < 86400) return `${Math.round(deltaSec / 3600)} h ago`;
  return new Date(ms).toLocaleString();
}
