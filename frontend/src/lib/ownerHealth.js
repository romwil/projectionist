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
 * One clear Library health narrative for the Admin hero.
 * Ties Named kinship, open issues, purge pressure, and Scheduled Tasks catch-up.
 *
 * @param {object} args
 * @param {object} [args.health]
 * @param {object} [args.coverage]
 * @param {number|null} [args.openIssues]
 * @param {number|null} [args.purgeCount]
 * @returns {{headline:string, body:string, tone:string}|null}
 */
export function buildLibraryHealthStory({ health, coverage, openIssues, purgeCount } = {}) {
  const h = health || {};
  const c = coverage || {};
  const explainable = pct(c.with_explainable_neighbors_pct);
  const overview = pct(c.with_overview_pct);
  const kinshipPct = explainable != null ? explainable : overview;
  const issues = typeof openIssues === "number" ? openIssues : null;
  const purge = typeof purgeCount === "number" ? purgeCount : null;
  const staleAdds = num(h.stale_adds);
  if (kinshipPct == null && issues == null && purge == null) return null;

  const bits = [];
  if (kinshipPct != null) {
    bits.push(
      kinshipPct < 50
        ? `Named kinship is at ${kinshipPct}% — empty More Like This shelves queue catch-up on Scheduled Tasks.`
        : `Named kinship is at ${kinshipPct}% — titles can cite a plot, crew, or collection link.`,
    );
  }
  if (issues != null) {
    bits.push(
      issues > 0
        ? `${issues} open issue${issues === 1 ? "" : "s"} need review.`
        : "No open media issues.",
    );
  }
  if (purge != null) {
    bits.push(
      purge > 0
        ? `${purge.toLocaleString()} purge candidate${purge === 1 ? "" : "s"} add disk pressure${
            staleAdds > 0 ? ` (${staleAdds.toLocaleString()} stale adds)` : ""
          }.`
        : "Purge buffer is clear.",
    );
  } else if (staleAdds > 0) {
    bits.push(`${staleAdds.toLocaleString()} stale adds still unwatched.`);
  }

  const warn =
    (kinshipPct != null && kinshipPct < 50) ||
    (issues != null && issues > 0) ||
    (purge != null && purge > 0);
  return {
    headline: "Library health",
    body: bits.join(" "),
    tone: warn ? "warn" : "good",
  };
}

/**
 * @param {object} args
 * @param {object} [args.health]   - GET /api/library/health payload
 * @param {object} [args.coverage] - GET /api/library/knowledge-coverage payload
 * @param {number|null} [args.openIssues] - open media-issue count (null = unknown)
 * @param {number|null} [args.purgeCount] - cached purge-candidate count (null = unknown)
 * @returns {Array<{id:string,label:string,value:string,detail:string,to:string,tone:string}>}
 */
export function buildHealthHeroTiles({ health, coverage, openIssues, purgeCount } = {}) {
  const h = health || {};
  const c = coverage || {};

  const total = num(h.total);
  const unwatched = pct(h.unwatched_pct);
  const rating = pct(h.rating_coverage_pct);
  // Named kinship is the health that matters for More Like This / inbox bridges.
  const explainable = pct(c.with_explainable_neighbors_pct);
  const overview = pct(c.with_overview_pct);
  const kinshipPct = explainable != null ? explainable : overview;
  const issues = typeof openIssues === "number" ? openIssues : null;
  const purge = typeof purgeCount === "number" ? purgeCount : null;
  const ratingNote =
    typeof h.rating_coverage_note === "string" && h.rating_coverage_note.trim()
      ? h.rating_coverage_note.trim()
      : null;

  const tiles = [
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
      label: "Named kinship",
      value: kinshipPct == null ? "—" : `${kinshipPct}%`,
      detail:
        explainable != null
          ? "Titles with a named More Like This link"
          : "Overview coverage",
      to: "/admin/scheduled-tasks",
      tone: kinshipPct != null && kinshipPct < 50 ? "warn" : "good",
    },
    {
      id: "issues",
      label: "Open issues",
      value: issues == null ? "—" : String(issues),
      detail: issues ? "Needs review" : "All clear",
      to: "/admin/health?tab=issues",
      tone: issues ? "warn" : "good",
    },
    {
      id: "purge",
      label: "Purge pressure",
      value: purge == null ? "—" : String(purge),
      detail: purge ? "Candidates in buffer" : "Buffer clear",
      to: "/admin#storage-intelligence",
      tone: purge ? "warn" : "good",
    },
    {
      id: "rating",
      label: "Rating coverage",
      value: rating == null ? "—" : `${rating}%`,
      detail: ratingNote || "Watched titles rated",
      to: browseHref({ watch_state: "watched" }),
      tone: ratingNote ? "warn" : "neutral",
    },
  ];
  return tiles;
}
