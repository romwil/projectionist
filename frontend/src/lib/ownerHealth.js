/** Derive the at-a-glance owner health hero tiles from existing aggregations.
 *
 * Pure logic so it can be unit-tested without rendering. Each tile links into the
 * relevant admin / browse surface; callers render them into the dashboard hero.
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

function browseHref({ watch_state, sort, sort_dir } = {}) {
  const params = new URLSearchParams();
  if (watch_state) params.set("watch_state", watch_state);
  if (sort) params.set("sort", sort);
  if (sort_dir) params.set("sort_dir", sort_dir);
  const query = params.toString();
  return query ? `/explore/browse?${query}` : "/explore/browse";
}

/**
 * @param {object} args
 * @param {object} [args.health]   - GET /api/library/health payload
 * @param {object} [args.coverage] - GET /api/library/knowledge-coverage payload
 * @param {number|null} [args.openIssues] - open media-issue count (null = unknown)
 * @returns {Array<{id:string,label:string,value:string,detail:string,to:string,tone:string}>}
 */
export function buildHealthHeroTiles({ health, coverage, openIssues } = {}) {
  const h = health || {};
  const c = coverage || {};

  const total = num(h.total);
  const unwatched = pct(h.unwatched_pct);
  const rating = pct(h.rating_coverage_pct);
  const overview = pct(c.with_overview_pct);
  const issues = typeof openIssues === "number" ? openIssues : null;
  const ratingNote =
    typeof h.rating_coverage_note === "string" && h.rating_coverage_note.trim()
      ? h.rating_coverage_note.trim()
      : null;

  return [
    {
      id: "titles",
      label: "Titles indexed",
      value: total ? total.toLocaleString() : "—",
      detail: `${num(h.watched_count).toLocaleString()} watched`,
      to: browseHref(),
      tone: "neutral",
    },
    {
      id: "unwatched",
      label: "Unwatched",
      value: unwatched == null ? "—" : `${unwatched}%`,
      detail: `${num(h.stale_adds).toLocaleString()} stale adds`,
      to: browseHref({ watch_state: "unwatched", sort: "added_at", sort_dir: "asc" }),
      tone: unwatched != null && unwatched >= 70 ? "warn" : "neutral",
    },
    {
      id: "coverage",
      label: "Plot knowledge",
      value: overview == null ? "—" : `${overview}%`,
      detail: "Overview coverage",
      to: "/admin/taxonomy",
      tone: overview != null && overview < 50 ? "warn" : "good",
    },
    {
      id: "rating",
      label: "Rating coverage",
      value: rating == null ? "—" : `${rating}%`,
      detail: ratingNote || "Watched titles rated",
      to: browseHref({ watch_state: "watched" }),
      tone: ratingNote ? "warn" : "neutral",
    },
    {
      id: "issues",
      label: "Open issues",
      value: issues == null ? "—" : String(issues),
      detail: issues ? "Needs review" : "All clear",
      to: "/admin/issues",
      tone: issues ? "warn" : "good",
    },
  ];
}
