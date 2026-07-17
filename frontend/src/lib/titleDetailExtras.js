/** Pure helpers for title-detail completeness (progress, collection, reviews CTA). */

export function formatTvProgress(detail) {
  const total = Number(detail?.total_episode_count);
  const unwatched = Number(detail?.unwatched_episode_count);
  if (!Number.isFinite(total) || total <= 0) return null;
  const remaining = Number.isFinite(unwatched) ? Math.max(0, unwatched) : null;
  const watched =
    remaining == null ? null : Math.min(total, Math.max(0, total - remaining));
  const pct =
    watched == null ? null : Math.round((watched / total) * 100);
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
  const selfKey = [
    detail?.tmdb_id,
    detail?.rating_key,
    detail?.title,
    detail?.year,
  ]
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

export function reviewsCtaForDetail(detail) {
  if (!detail?.in_library) return null;
  if (detail.user_stars != null && Number(detail.user_stars) > 0) {
    return {
      kind: "rated",
      label: `Your rating: ${detail.user_stars}★`,
      href: null,
    };
  }
  return {
    kind: "rate",
    label: "Leave a review",
    href: "/?rate=1",
  };
}
