/**
 * Pure helpers for the generalized notifications inbox.
 * Kinds: recommendation | arrival | access-request | digest | nudge
 */

export const NOTIFICATION_KINDS = [
  "recommendation",
  "arrival",
  "access-request",
  "digest",
  "nudge",
];

export function recommendationIdentity(item) {
  const type = item?.media_type === "show" ? "show" : "movie";
  const externalId = item?.tmdb_id || item?.tvdb_id || item?.rating_key || item?.plex_rating_key;
  return externalId
    ? `${type}:${externalId}`
    : `${type}:${String(item?.title || "").trim().toLowerCase()}:${item?.year || ""}`;
}

export function notificationIdentity(item) {
  if (item?.id) return `id:${item.id}`;
  const kind = String(item?.kind || "recommendation");
  if (kind === "recommendation") return `rec:${recommendationIdentity(item)}`;
  if (item?.related_id) return `${kind}:${item.related_id}`;
  return `${kind}:${String(item?.title || "").trim().toLowerCase()}:${item?.created_at || ""}`;
}

export function dedupeRecommendations(items = []) {
  const byIdentity = new Map();
  for (const item of items) {
    const key = recommendationIdentity(item);
    const current = byIdentity.get(key);
    if (!current || String(item?.message || item?.body || "").length > String(current?.message || current?.body || "").length) {
      byIdentity.set(key, item);
    }
  }
  return [...byIdentity.values()];
}

export function dedupeNotifications(items = []) {
  const byIdentity = new Map();
  for (const item of items) {
    const key = notificationIdentity(item);
    if (!byIdentity.has(key)) byIdentity.set(key, item);
  }
  return [...byIdentity.values()];
}

export function normalizeRecommendation(item) {
  return {
    ...item,
    kind: item?.kind || "recommendation",
    in_library: item?.in_library ?? Boolean(item?.rating_key || item?.plex_rating_key),
    message: item?.message ?? item?.body ?? null,
    body: item?.body ?? item?.message ?? null,
  };
}

export function inboxHeadline(items = []) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return "Inbox";
  if (list.length === 1) {
    const kind = String(list[0]?.kind || "recommendation");
    if (kind === "arrival") return "Something new arrived";
    if (kind === "digest") return "You have a digest";
    if (kind === "access-request") return "Someone requested access";
    if (kind === "nudge") return "A curator nudge for you";
    return "Someone recommended a title";
  }
  return `${list.length} new notifications`;
}

export function inboxCardCopy(item) {
  const kind = String(item?.kind || "recommendation");
  const fromName = item?.from_display_name || "Someone";
  const yearBit = item?.year ? ` (${item.year})` : "";
  const title = item?.title || "a title";
  if (kind === "arrival") {
    return { eyebrow: "Arrival", lead: title, note: item?.body || item?.message || null };
  }
  if (kind === "digest") {
    return { eyebrow: "Digest", lead: title, note: item?.body || item?.message || null };
  }
  if (kind === "access-request") {
    return {
      eyebrow: "Access request",
      lead: title,
      note: item?.body || item?.message || null,
    };
  }
  if (kind === "nudge") {
    return { eyebrow: "Nudge", lead: title, note: item?.body || item?.message || null };
  }
  return {
    eyebrow: "Recommendation",
    lead: (
      // Plain string for non-JSX consumers; RecommendationsInbox may override.
      null
    ),
    leadText: `${fromName} recommended ${title}${yearBit} for you`,
    note: item?.message || item?.body || null,
    fromName,
    title,
    yearBit,
  };
}

export function formatUnreadBadge(count) {
  const n = Number(count) || 0;
  if (n <= 0) return "";
  if (n > 99) return "99+";
  return String(n);
}
