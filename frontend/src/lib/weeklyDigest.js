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

/** Dedupe new-addition chips by tmdb identity, else title+year. */
export function dedupeDigestTitles(titles) {
  if (!Array.isArray(titles)) return [];
  const seen = new Set();
  const out = [];
  for (const item of titles) {
    if (!item || typeof item !== "object") continue;
    let key;
    if (item.tmdb_id != null && item.tmdb_id !== "") {
      key = `tmdb:${item.tmdb_id}:${String(item.media_type || "").toLowerCase()}`;
    } else {
      const title = String(item.title || "").trim().toLowerCase();
      const year = item.year != null && item.year !== "" ? String(item.year) : "";
      key = `title:${title}|${year}`;
    }
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

/**
 * @param {object|null} latest - { generated_at, week_start, payload } | null
 * @returns {null | {
 *   generatedAt: number|null,
 *   library: {total:number,movies:number,shows:number},
 *   newTitles: Array<{title:string,year:any,media_type:any}>,
 *   newCount: number,
 *   stats: Array<{id:string,label:string,value:string,to:string}>,
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
  const rawTitles = Array.isArray(newThisWeek.titles) ? newThisWeek.titles : [];
  const newTitles = dedupeDigestTitles(rawTitles).slice(0, 8);

  return {
    generatedAt: latest.generated_at ?? payload.generated_at ?? null,
    weekStart: latest.week_start ?? null,
    library: {
      total: num(library.total),
      movies: num(library.movies),
      shows: num(library.shows),
    },
    newCount: num(newThisWeek.count),
    newTitles,
    stats: [
      {
        id: "new",
        label: "Added this week",
        value: String(num(newThisWeek.count)),
        to: "/explore/section/recently-added",
      },
      {
        id: "open-issues",
        label: "Open issues",
        value: String(num(issues.open)),
        to: "/admin/health?tab=issues",
      },
      {
        id: "unwatched",
        label: "Unwatched",
        value: unwatched == null ? "—" : `${unwatched}%`,
        to: "/explore/browse?watch_state=unwatched&sort=added_at&sort_dir=asc",
      },
      {
        id: "coverage",
        label: "Plot knowledge",
        value: overview == null ? "—" : `${overview}%`,
        to: "/admin/taxonomy",
      },
      {
        id: "purge",
        label: "Purge candidates",
        value: String(num(purge.candidates)),
        to: "/admin/health?tab=sync#storage-intelligence",
      },
    ],
  };
}
