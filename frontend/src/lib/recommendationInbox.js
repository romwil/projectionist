/**
 * Pure helpers for the generalized notifications inbox.
 * Kinds: recommendation | arrival | access-request | digest | nudge | library-share | year-in-review
 */

import { isWatchPartyRecommendation, recommendationIntent } from "./householdSocial.js";

export const NOTIFICATION_KINDS = [
  "recommendation",
  "arrival",
  "access-request",
  "digest",
  "nudge",
  "library-share",
  "year-in-review",
];

/**
 * Inbox page fetch contract. Dismiss sets seen_at; loading history
 * (unread_only: false) made clear-all appear to undo on reopen.
 */
export const INBOX_LIST_PARAMS = Object.freeze({ unread_only: true, limit: 50 });

export const ACCESS_REQUEST_ADMIN_PATH = "/admin/access";
export const LIVE_CHANNELS_PATH = "/live";

export { isWatchPartyRecommendation, recommendationIntent };

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
    intent: recommendationIntent(item),
    in_library: item?.in_library ?? Boolean(item?.rating_key || item?.plex_rating_key),
    message: item?.message ?? item?.body ?? null,
    body: item?.body ?? item?.message ?? null,
  };
}

/**
 * Media title for recommendation cards.
 * Legacy inbox rows stored a precomposed "{name} recommended {title} ({year})"
 * sentence in `title`; strip that so cardLead does not double-compose.
 */
export function recommendationMediaTitle(item) {
  const raw = String(item?.title || "").trim();
  if (!raw) return "";
  const fromName = String(item?.from_display_name || "").trim();
  let media = raw;
  if (fromName) {
    const prefix = `${fromName} recommended `;
    if (raw.toLowerCase().startsWith(prefix.toLowerCase())) {
      media = raw.slice(prefix.length).trim();
    }
  }
  if (media === raw) {
    const match = raw.match(/\brecommended\s+(.+)$/i);
    if (match) media = match[1].trim();
  }
  const year = item?.year;
  if (year != null && year !== "") {
    const yearSuffix = ` (${year})`;
    if (media.endsWith(yearSuffix)) {
      media = media.slice(0, -yearSuffix.length).trim();
    }
  }
  return media || raw;
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
    if (kind === "library-share") return "Someone shared a saved page";
    if (kind === "year-in-review") return "Your Year in Review is ready";
    if (kind === "recommendation" && isWatchPartyRecommendation(list[0])) {
      return "Someone invited you to watch together";
    }
    return "Someone recommended a title";
  }
  return `${list.length} new notifications`;
}

/** First sentence / short lead from a multi-line note (never the full digest email). */
export function firstSentence(text, { maxLen = 160 } = {}) {
  const raw = String(text || "").replace(/\s+/g, " ").trim();
  if (!raw) return "";
  const match = raw.match(/^(.+?[.!?])(?:\s|$)/);
  const sentence = (match ? match[1] : raw).trim();
  if (sentence.length <= maxLen) return sentence;
  return `${sentence.slice(0, Math.max(1, maxLen - 1)).trimEnd()}…`;
}

/**
 * Normalize digest payload.picks for the pick strip.
 * Fail-closed: skip rows without tmdb_id / rating_key / tvdb_id.
 */
export function digestPicks(item, { limit = 8 } = {}) {
  const raw = item?.payload?.picks;
  if (!Array.isArray(raw)) return [];
  const picks = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const title = String(entry.title || "").trim();
    if (!title) continue;
    const tmdbId = entry.tmdb_id != null && entry.tmdb_id !== "" ? Number(entry.tmdb_id) : null;
    const ratingKey = String(entry.rating_key || entry.plex_rating_key || "").trim() || null;
    const tvdbId = entry.tvdb_id != null && entry.tvdb_id !== "" ? Number(entry.tvdb_id) : null;
    if ((tmdbId == null || Number.isNaN(tmdbId)) && !ratingKey && (tvdbId == null || Number.isNaN(tvdbId))) {
      continue;
    }
    const mediaType = entry.media_type === "show" ? "show" : "movie";
    const poster = String(entry.poster_url || entry.poster_path || "").trim() || null;
    const year = entry.year != null && entry.year !== "" ? Number(entry.year) : null;
    picks.push({
      title,
      media_type: mediaType,
      tmdb_id: tmdbId != null && !Number.isNaN(tmdbId) ? tmdbId : null,
      rating_key: ratingKey,
      tvdb_id: tvdbId != null && !Number.isNaN(tvdbId) ? tvdbId : null,
      year: year != null && !Number.isNaN(year) ? year : null,
      poster_url: poster,
    });
    if (picks.length >= limit) break;
  }
  return picks;
}

export function digestBlurb(item) {
  const fromPayload = String(item?.payload?.blurb || "").trim();
  if (fromPayload) return firstSentence(fromPayload);
  return firstSentence(item?.body || item?.message || "");
}

export function isLiveChannelsNudge(item) {
  if (String(item?.kind || "") !== "nudge") return false;
  const payload = item?.payload || {};
  if (payload.live_channels === true) return true;
  const cta = String(payload.cta || "").trim();
  return cta === "/live" || cta === "plex_live_tv" || cta === "live";
}

export function isEnthusiastNudge(item) {
  return String(item?.kind || "") === "nudge" && Boolean(item?.payload?.enthusiast);
}

/** Visible note for nudge cards — never a recently-watched comma dump. */
export function nudgeCardNote(item) {
  if (isLiveChannelsNudge(item)) {
    return firstSentence(item?.body || item?.message || "");
  }
  if (isEnthusiastNudge(item)) {
    const why = String(item?.payload?.pick_why || "").trim();
    if (why) return firstSentence(why);
    // Prefer a short why line from body; never surface "recently watched: A, B".
    const body = String(item?.body || item?.message || "");
    const lines = body
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line) => !/recently watched/i.test(line));
    const candidate = lines.find((line) => !/^open curatorx/i.test(line) && !/opt-in nudge/i.test(line));
    return candidate ? firstSentence(candidate) : null;
  }
  return firstSentence(item?.body || item?.message || "") || null;
}

/**
 * Primary CTA for event cards (href + label). Owner-only for access-request.
 */
export function eventPrimaryCta(item, { role } = {}) {
  const kind = String(item?.kind || "recommendation");
  if (kind === "access-request") {
    if (role && role !== "owner") return null;
    return {
      href: ACCESS_REQUEST_ADMIN_PATH,
      label: "Review request",
      testIdSuffix: "review-access",
    };
  }
  if (kind === "nudge" && isLiveChannelsNudge(item)) {
    const cta = String(item?.payload?.cta || "").trim();
    const href = cta.startsWith("/") ? cta : LIVE_CHANNELS_PATH;
    return {
      href,
      label: "Open Live",
      testIdSuffix: "open-live",
    };
  }
  if (kind === "library-share") {
    const path =
      item?.payload?.path ||
      (item?.payload?.page_id ? `/library/${encodeURIComponent(item.payload.page_id)}` : null);
    if (!path) return null;
    return {
      href: path,
      label: "Open saved page",
      testIdSuffix: "open-library",
    };
  }
  if (kind === "year-in-review") {
    const path =
      item?.payload?.path ||
      (item?.payload?.year ? `/year-in-review/${encodeURIComponent(item.payload.year)}` : null);
    if (!path) return null;
    return {
      href: path,
      label: "Open Year in Review",
      testIdSuffix: "open-yir",
    };
  }
  return null;
}

export function inboxCardCopy(item) {
  const kind = String(item?.kind || "recommendation");
  const fromName = item?.from_display_name || "Someone";
  const yearBit = item?.year ? ` (${item.year})` : "";
  const title = kind === "recommendation" ? recommendationMediaTitle(item) || "a title" : item?.title || "a title";
  if (kind === "arrival") {
    return { eyebrow: "Arrival", lead: title, note: item?.body || item?.message || null };
  }
  if (kind === "digest") {
    const picks = digestPicks(item);
    return {
      eyebrow: "Digest",
      lead: picks.length ? `This week for you · ${picks.length} pick${picks.length === 1 ? "" : "s"}` : title,
      note: digestBlurb(item) || null,
      picks,
    };
  }
  if (kind === "access-request") {
    return {
      eyebrow: "Access request",
      lead: title,
      note: firstSentence(item?.body || item?.message || "") || null,
    };
  }
  if (kind === "nudge") {
    return {
      eyebrow: isLiveChannelsNudge(item) ? "Live Channels" : "Nudge",
      lead: title,
      note: nudgeCardNote(item),
    };
  }
  if (kind === "library-share") {
    return {
      eyebrow: "Shared page",
      lead: title,
      note: item?.body || item?.message || null,
      path: item?.payload?.path || (item?.payload?.page_id ? `/library/${item.payload.page_id}` : null),
    };
  }
  if (kind === "year-in-review") {
    return {
      eyebrow: "Year in Review",
      lead: title,
      note: firstSentence(item?.body || item?.message || "") || null,
      path: item?.payload?.path || (item?.year ? `/year-in-review/${item.year}` : null),
    };
  }
  const watchParty = isWatchPartyRecommendation(item);
  return {
    eyebrow: watchParty ? "Watch together" : "Recommendation",
    lead: null,
    leadText: watchParty
      ? `${fromName} invited you to watch ${title}${yearBit}`
      : `${fromName} recommended ${title}${yearBit} for you`,
    note: item?.message || item?.body || null,
    fromName,
    title,
    yearBit,
    intent: recommendationIntent(item),
  };
}

export function formatUnreadBadge(count) {
  const n = Number(count) || 0;
  if (n <= 0) return "";
  if (n > 99) return "99+";
  return String(n);
}
