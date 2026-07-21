/** Normalize the weekly in-app digest payload into a display model. Pure logic. */

function pct(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return Math.round(num);
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatDigestTitle(item) {
  if (!item) return "";
  const name = String(item.title || "Untitled");
  return item.year ? `${name} (${item.year})` : name;
}

/**
 * @param {object|null} latest - { generated_at, week_start, payload } | null
 * @returns {null | {
 *   generatedAt: number|null,
 *   library: {total:number,movies:number,shows:number},
 *   newTitles: Array<{title:string,year:any,media_type:any}>,
 *   newCount: number,
 *   stats: Array<{id:string,label:string,value:string}>,
 * }}
 */
export function normalizeWeeklyDigest(latest) {
  if (!latest || typeof latest !== "object") return null;
  const payload = latest.payload || {};
  const library = payload.library || {};
  const health = payload.health || {};
  const coverage = payload.coverage || {};
  const issues = payload.issues || {};
  const newThisWeek = payload.new_this_week || {};
  const purge = payload.purge || {};

  const overview = pct(coverage.with_overview_pct);
  const unwatched = pct(health.unwatched_pct);

  return {
    generatedAt: latest.generated_at ?? payload.generated_at ?? null,
    weekStart: latest.week_start ?? null,
    library: {
      total: num(library.total),
      movies: num(library.movies),
      shows: num(library.shows),
    },
    newCount: num(newThisWeek.count),
    newTitles: Array.isArray(newThisWeek.titles) ? newThisWeek.titles.slice(0, 8) : [],
    stats: [
      { id: "new", label: "Added this week", value: String(num(newThisWeek.count)) },
      { id: "open-issues", label: "Open issues", value: String(num(issues.open)) },
      {
        id: "unwatched",
        label: "Unwatched",
        value: unwatched == null ? "—" : `${unwatched}%`,
      },
      {
        id: "coverage",
        label: "Plot knowledge",
        value: overview == null ? "—" : `${overview}%`,
      },
      { id: "purge", label: "Purge candidates", value: String(num(purge.candidates)) },
    ],
  };
}
