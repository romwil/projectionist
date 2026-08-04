/**
 * Admin overview “household health” hero chips — library + Live readiness.
 * Pure helpers for unit tests; ConfigPage renders the tiles.
 */

function pct(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return Math.max(0, Math.min(100, Math.round(num)));
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Live readiness chip state for the household health hero.
 * @param {{ liveEnabled?: boolean, liveReady?: boolean, stationCount?: number }} args
 */
export function liveReadinessChip({ liveEnabled = false, liveReady = false, stationCount = 0 } = {}) {
  if (liveReady) {
    const stations = num(stationCount);
    return {
      id: "live",
      label: "Live",
      value: "On air",
      detail: stations > 0 ? `${stations} station${stations === 1 ? "" : "s"}` : "Ready to watch",
      to: "/admin/live-channels",
      tone: "good",
    };
  }
  if (liveEnabled) {
    return {
      id: "live",
      label: "Live",
      value: "Warming",
      detail: "Finish Setup to put stations on air",
      to: "/admin/live-channels",
      tone: "warn",
    };
  }
  return {
    id: "live",
    label: "Live",
    value: "Off",
    detail: "Put your library on the air",
    to: "/admin/live-channels",
    tone: "neutral",
  };
}

/**
 * @param {object} args
 * @param {object} [args.libraryHealth] - GET /api/library/health
 * @param {object} [args.libraryStats] - movies/shows/last_sync
 * @param {boolean} [args.plexConnected]
 * @param {number} [args.sectionsCount]
 * @param {boolean} [args.liveEnabled]
 * @param {boolean} [args.liveReady]
 * @param {number} [args.stationCount]
 * @returns {Array<{id:string,label:string,value:string,detail:string,to:string,tone:string}>}
 */
export function buildHouseholdHealthChips({
  libraryHealth,
  libraryStats,
  plexConnected = false,
  sectionsCount = 0,
  liveEnabled = false,
  liveReady = false,
  stationCount = 0,
} = {}) {
  const h = libraryHealth || {};
  const stats = libraryStats || {};
  const total = num(h.total) || num(stats.movies) + num(stats.shows);
  const unwatched = pct(h.unwatched_pct);
  const rating = pct(h.rating_coverage_pct);
  const libraries = num(sectionsCount);

  return [
    {
      id: "plex",
      label: "Plex",
      value: plexConnected ? "Connected" : "Needs setup",
      detail: plexConnected
        ? libraries > 0
          ? `${libraries} librar${libraries === 1 ? "y" : "ies"} mapped`
          : "Map libraries next"
        : "Add a server token under Connections",
      to: "/admin/connections",
      tone: plexConnected ? "good" : "warn",
    },
    {
      id: "library",
      label: "Indexed",
      value: total ? total.toLocaleString() : "—",
      detail: stats.last_sync
        ? `${num(stats.movies)} movies · ${num(stats.shows)} shows`
        : "Run Sync library after Plex is connected",
      to: "/admin/libraries",
      tone: total ? "neutral" : "warn",
    },
    {
      id: "unwatched",
      label: "Unwatched",
      value: unwatched == null ? "—" : `${unwatched}%`,
      detail: `${num(h.stale_adds).toLocaleString()} never played`,
      to: "/admin/dashboard",
      tone: unwatched != null && unwatched >= 70 ? "warn" : "neutral",
    },
    {
      id: "rating",
      label: "Rated",
      value: rating == null ? "—" : `${rating}%`,
      detail: "Of watched titles",
      to: "/admin/dashboard",
      tone: "neutral",
    },
    liveReadinessChip({ liveEnabled, liveReady, stationCount }),
  ];
}
