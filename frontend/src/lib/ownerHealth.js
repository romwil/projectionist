/** Derive the at-a-glance owner "Library health" hero tiles from existing aggregations.
 *
 * Pure logic so it can be unit-tested without rendering. Each tile links into the
 * relevant admin surface; callers render them into the dashboard hero.
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
 * @param {object} args
 * @param {object} [args.health]   - GET /api/library/health payload
 * @param {object} [args.coverage] - GET /api/library/knowledge-coverage payload
 * @param {number} [args.streak]   - engagement streak count
 * @param {number|null} [args.openIssues] - open media-issue count (null = unknown)
 * @returns {Array<{id:string,label:string,value:string,detail:string,to:string,tone:string}>}
 */
export function buildHealthHeroTiles({ health, coverage, streak, openIssues } = {}) {
  const h = health || {};
  const c = coverage || {};

  const total = num(h.total);
  const unwatched = pct(h.unwatched_pct);
  const rating = pct(h.rating_coverage_pct);
  const overview = pct(c.with_overview_pct);
  const issues = typeof openIssues === "number" ? openIssues : null;
  const streakCount = num(streak);

  const tiles = [
    {
      id: "titles",
      label: "Titles indexed",
      value: total ? total.toLocaleString() : "—",
      detail: `${num(h.watched_count).toLocaleString()} watched`,
      to: "/admin/dashboard",
      tone: "neutral",
    },
    {
      id: "unwatched",
      label: "Unwatched",
      value: unwatched == null ? "—" : `${unwatched}%`,
      detail: `${num(h.stale_adds).toLocaleString()} stale adds`,
      to: "/admin/dashboard",
      tone: unwatched != null && unwatched >= 70 ? "warn" : "neutral",
    },
    {
      id: "coverage",
      label: "Plot knowledge",
      value: overview == null ? "—" : `${overview}%`,
      detail: "Overview coverage",
      to: "/admin/tasks",
      tone: overview != null && overview < 50 ? "warn" : "good",
    },
    {
      id: "rating",
      label: "Rating coverage",
      value: rating == null ? "—" : `${rating}%`,
      detail: "Watched titles rated",
      to: "/admin/dashboard",
      tone: "neutral",
    },
    {
      id: "issues",
      label: "Open issues",
      value: issues == null ? "—" : String(issues),
      detail: issues ? "Needs review" : "All clear",
      to: "/admin/issues",
      tone: issues ? "warn" : "good",
    },
    {
      id: "streak",
      label: "Curator streak",
      value: streakCount ? String(streakCount) : "—",
      detail: "Sessions · 30 days",
      to: "/admin/dashboard",
      tone: "neutral",
    },
  ];

  return tiles;
}
