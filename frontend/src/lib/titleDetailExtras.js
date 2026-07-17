/** Pure helpers for title-detail completeness (progress, collection, reviews CTA). */

import { normalizeUserRole } from "./addActions.js";
import { formatStarsLabel } from "./starRating.js";
import { libraryItemRatingKey } from "./bulkLibraryDelete.js";

const TITLE_CASE_MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Hero chip + Released meta: `YYYY Month D`, or year-only when no full date. */
export function formatTitleReleaseBadge({ releaseDate, firstAirDate, year, mediaType } = {}) {
  const dateValue =
    mediaType === "show"
      ? firstAirDate || releaseDate
      : releaseDate || firstAirDate;
  const raw = String(dateValue || "").trim();
  const match = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (match) {
    const y = Number(match[1]);
    const m = Number(match[2]);
    const d = Number(match[3]);
    const monthName = TITLE_CASE_MONTHS[m - 1];
    if (monthName && d >= 1 && d <= 31) {
      return `${y} ${monthName} ${d}`;
    }
  }
  if (year != null && String(year).trim()) return String(year);
  if (/^\d{4}$/.test(raw)) return raw;
  return null;
}

export function formatTvProgress(detail) {
  const total = Number(detail?.total_episode_count);
  const unwatched = Number(detail?.unwatched_episode_count);
  if (!Number.isFinite(total) || total <= 0) return null;
  const remaining = Number.isFinite(unwatched) ? Math.max(0, unwatched) : null;
  const watched =
    remaining == null ? null : Math.min(total, Math.max(0, total - remaining));
  const pct = watched == null ? null : Math.round((watched / total) * 100);
  return {
    total,
    unwatched: remaining,
    watched,
    pct,
    label:
      remaining == null
        ? `${total} episodes`
        : remaining === 0
          ? `Complete · ${total} episodes`
          : `${watched}/${total} watched · ${remaining} left`,
  };
}

/** Other library titles sharing a collection_name (excludes current). */
export function filterCollectionPeers(items, detail, { limit = 12 } = {}) {
  const name = String(detail?.collection_name || "").trim().toLowerCase();
  if (!name) return [];
  const selfKey = [detail?.tmdb_id, detail?.rating_key, detail?.title, detail?.year]
    .map((v) => String(v ?? ""))
    .join("|");
  const out = [];
  for (const item of Array.isArray(items) ? items : []) {
    const itemCollection = String(item?.collection_name || "").trim().toLowerCase();
    if (itemCollection !== name) continue;
    const key = [item?.tmdb_id, item?.rating_key, item?.title, item?.year]
      .map((v) => String(v ?? ""))
      .join("|");
    if (key === selfKey) continue;
    out.push(item);
    if (out.length >= limit) break;
  }
  return out;
}

/**
 * Reviews CTA for title detail.
 * Unrated library titles open an in-place editor (`action: "inline"`), not chat `/rate`.
 */
export function reviewsCtaForDetail(detail) {
  if (!detail?.in_library) return null;
  if (detail.user_stars != null && Number(detail.user_stars) > 0) {
    return {
      kind: "rated",
      label: `Your rating: ${formatStarsLabel(detail.user_stars)}★`,
      href: null,
      action: null,
    };
  }
  return {
    kind: "rate",
    label: "Leave a review",
    href: null,
    action: "inline",
  };
}

export function isTitleWatched(detail) {
  return Number(detail?.view_count || 0) > 0;
}

/** Guests cannot mutate household watch state when multi-user is on. */
export function canMarkTitleWatched(detail, { role, multiUserEnabled } = {}) {
  if (!detail?.in_library) return false;
  if (!libraryItemRatingKey(detail)) return false;
  const normalized = normalizeUserRole(role, { multiUserEnabled });
  if (multiUserEnabled && normalized === "guest") return false;
  return true;
}

export function watchedCtaLabel(detail) {
  return isTitleWatched(detail) ? "Mark as unwatched" : "Mark as watched";
}
