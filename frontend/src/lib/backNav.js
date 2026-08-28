/** Shared return-navigation helpers for browse / detail pages. */

import {
  CHAT_FROM_RAIL_ID_PARAM,
  CHAT_FROM_RAIL_PACK_PARAM,
  buildRailChatPrompt,
  decodeRailPack,
  encodeRailPack,
  expandRailItem,
  stashRailSeed,
} from "./railChatSeed.js";

export const ROUTES = {
  chat: "/chat",
  search: "/search",
  inbox: "/inbox",
  myJourney: "/my-journey",
  explore: "/explore",
  tags: "/explore/tags",
  relatedTitles: "/explore/related",
  plotLab: "/explore/plot-lab",
  libraryBrowse: "/explore/browse",
  /** @deprecated Prefer ROUTES.myJourney — legacy engagement path redirects. */
  engagement: "/explore/engagement",
  live: "/live",
  liveWatch: "/live/watch",
  watchlist: "/watchlist",
  library: "/library",
  tour: "/login",
  /** Sync/token settings only — browse pins on /watchlist. */
  watchlistSettings: "/settings/watchlist",
  settings: "/settings",
  admin: "/admin",
  adminTasks: "/admin/tasks",
  adminHealth: "/admin/health",
  /** @deprecated Prefer adminHealth with ?tab=sync */
  adminDashboard: "/admin/health?tab=sync",
  /** @deprecated Prefer adminHealth with ?tab=usage */
  adminUsage: "/admin/health?tab=usage",
  adminLogs: "/admin/logs",
  about: "/about",
  help: "/help",
  privacy: "/privacy",
};

/**
 * Deep-link to a specific Help section anchor. Pass a slug (see
 * frontend/src/lib/helpAnchors.js) matching a docs/HELP.md heading; omit it for
 * the top of Help.
 */
export function helpAnchor(anchor = "") {
  const slug = String(anchor || "").replace(/^#/, "").trim();
  return slug ? `${ROUTES.help}#${slug}` : ROUTES.help;
}

/** @deprecated Use ROUTES.watchlist — kept for legacy deep links. */
export const WATCHLIST_PANEL_PARAM = "watchlist";

/** @deprecated Opens chat with legacy panel flag; redirects to /watchlist in App. */
export function watchlistPanelHref() {
  return `${ROUTES.chat}?${WATCHLIST_PANEL_PARAM}=1`;
}

/** Query flag that opens the /rate review batch flow in chat. */
export const RATE_FLOW_PARAM = "rate";

/** Chat deep-link parameters for discussing recommendations like one title. */
export const RECOMMEND_LIKE_PARAM = "recommend_like";
const RECOMMEND_LIKE_YEAR_PARAM = "year";
const RECOMMEND_LIKE_TYPE_PARAM = "type";

/** Deep-link to the watchlist browse page. */
export function watchlistBrowseHref() {
  return ROUTES.watchlist;
}

/** Deep-link to chat that triggers the rate / review batch flow. */
export function rateFlowHref() {
  return `${ROUTES.chat}?${RATE_FLOW_PARAM}=1`;
}

/** Deep-link to chat and seed a discussion based on a library title. */
export function recommendLikeHref(item) {
  const params = new URLSearchParams();
  const title = String(item?.title || "").trim();
  if (!title) return ROUTES.chat;
  params.set(RECOMMEND_LIKE_PARAM, title);
  if (item?.year) params.set(RECOMMEND_LIKE_YEAR_PARAM, String(item.year));
  if (item?.media_type) params.set(RECOMMEND_LIKE_TYPE_PARAM, String(item.media_type));
  return `${ROUTES.chat}?${params.toString()}`;
}

/** Build the user-visible seeded request from a recommendation-like URL. */
export function recommendLikePrompt(searchParams) {
  if (!searchParams || typeof searchParams.get !== "function") return "";
  const title = String(searchParams.get(RECOMMEND_LIKE_PARAM) || "").trim();
  if (!title) return "";
  const details = [
    String(searchParams.get(RECOMMEND_LIKE_YEAR_PARAM) || "").trim(),
    String(searchParams.get(RECOMMEND_LIKE_TYPE_PARAM) || "").trim(),
  ].filter(Boolean);
  return `Recommend titles like "${title}"${details.length ? ` (${details.join(", ")})` : ""} and help me discuss what makes it work.`;
}

/** Query flag that opens chat seeded from an Explore rail. */
export const CHAT_FROM_RAIL_PARAM = "from_rail";
const CHAT_FROM_RAIL_TITLE_PARAM = "rail_title";
const CHAT_FROM_RAIL_WHY_PARAM = "rail_why";

/**
 * Default discuss opener for Chat about this (single title → /chat).
 * Stored as focus why so buildRailChatPrompt leads with "Let's discuss"
 * without repeating a redundant curator-why clause.
 */
export const CHAT_ABOUT_TITLE_WHY = "Let's discuss this";

/**
 * Normalize a poster/card/detail into a rail-seed item for Chat about this.
 * Prefers library_item_id (title detail) then id; keeps tmdb / media_type / rating_key.
 * @param {Record<string, unknown> | null | undefined} item
 */
export function chatAboutTitleSeed(item) {
  if (!item || typeof item !== "object") return null;
  const title = String(item.title || "").trim();
  if (!title) return null;
  const libraryIdRaw = item.library_item_id ?? item.id;
  const libraryId =
    libraryIdRaw != null && Number.isFinite(Number(libraryIdRaw)) ? Number(libraryIdRaw) : undefined;
  const ratingKey = String(item.rating_key || item.plex_rating_key || "").trim();
  const why = String(item.why || item.recommendation_reason || "").trim();
  return {
    title,
    year: item.year,
    media_type: item.media_type,
    id: libraryId,
    library_item_id: libraryId,
    rating_key: ratingKey || undefined,
    tmdb_id: item.tmdb_id,
    tvdb_id: item.tvdb_id,
    poster_url: item.poster_url || item.thumb || "",
    backdrop_url: item.backdrop_url || item.art || "",
    in_library: Boolean(item.in_library ?? (Boolean(ratingKey) || libraryId != null)),
    why: why || CHAT_ABOUT_TITLE_WHY,
    recommendation_reason: why || undefined,
  };
}

/**
 * Deep-link to default Chat with one title loaded (same rail_pack transport as
 * Explore "Chat about these") and a discuss opener as the opening user message.
 * @param {Record<string, unknown> | null | undefined} item
 */
export function chatAboutTitleHref(item) {
  const seed = chatAboutTitleSeed(item);
  if (!seed) return ROUTES.chat;
  const railId =
    seed.id != null
      ? `title-${seed.id}`
      : seed.rating_key
        ? `rk-${seed.rating_key}`
        : seed.tmdb_id != null
          ? `tmdb-${seed.media_type || "movie"}-${seed.tmdb_id}`
          : "about-title";
  return chatFromRailHref({ railTitle: seed.title, railId, items: [seed] }, seed);
}

/**
 * Deep-link to chat with rail context (stable ids + why per title).
 * Also stashes full items (posters) in sessionStorage for the chat turn.
 * @param {{ railTitle?: string, railId?: string, items?: Array<Record<string, unknown>> }} rail
 * @param {{ title?: string, why?: string, rating_key?: string, id?: number } | null} [focusItem]
 */
export function chatFromRailHref(rail, focusItem = null) {
  const params = new URLSearchParams();
  const railTitle = String(rail?.railTitle || rail?.title || "this rail").trim();
  params.set(CHAT_FROM_RAIL_PARAM, "1");
  params.set(CHAT_FROM_RAIL_TITLE_PARAM, railTitle.slice(0, 120));
  const railId = String(rail?.railId || rail?.id || "").trim();
  if (railId) params.set(CHAT_FROM_RAIL_ID_PARAM, railId.slice(0, 64));

  const sourceItems = Array.isArray(rail?.items) ? rail.items : [];
  stashRailSeed({ railTitle, railId, items: sourceItems });

  const pack = encodeRailPack(focusItem?.title ? [focusItem, ...sourceItems] : sourceItems);
  if (pack) params.set(CHAT_FROM_RAIL_PACK_PARAM, pack);

  if (focusItem?.title) {
    params.set(RECOMMEND_LIKE_PARAM, String(focusItem.title).trim().slice(0, 120));
    const why = focusItem.why || focusItem.recommendation_reason;
    if (why) {
      params.set(CHAT_FROM_RAIL_WHY_PARAM, String(why).trim().slice(0, 280));
    }
    if (focusItem.year) params.set(RECOMMEND_LIKE_YEAR_PARAM, String(focusItem.year));
    if (focusItem.media_type) params.set(RECOMMEND_LIKE_TYPE_PARAM, String(focusItem.media_type));
  } else {
    const titles = sourceItems
      .map((item) => String(item?.title || "").trim())
      .filter(Boolean)
      .slice(0, 8);
    if (titles.length) {
      params.set("rail_titles", titles.join("|").slice(0, 400));
    }
  }
  return `${ROUTES.chat}?${params.toString()}`;
}

/** Decode curated items from a chat-from-rail URL (pack preferred, titles fallback). */
export function chatFromRailItems(searchParams) {
  if (!searchParams || typeof searchParams.get !== "function") return [];
  if (String(searchParams.get(CHAT_FROM_RAIL_PARAM) || "") !== "1") return [];
  const packed = decodeRailPack(searchParams.get(CHAT_FROM_RAIL_PACK_PARAM));
  if (packed.length) return packed;
  return String(searchParams.get("rail_titles") || "")
    .split("|")
    .map((t) => t.trim())
    .filter(Boolean)
    .map((title) => expandRailItem({ t: title }))
    .filter(Boolean);
}

/** Build the seeded chat prompt from a chat-from-rail URL. */
export function chatFromRailPrompt(searchParams) {
  if (!searchParams || typeof searchParams.get !== "function") return "";
  if (String(searchParams.get(CHAT_FROM_RAIL_PARAM) || "") !== "1") return "";
  const railTitle = String(searchParams.get(CHAT_FROM_RAIL_TITLE_PARAM) || "this rail").trim();
  const focus = String(searchParams.get(RECOMMEND_LIKE_PARAM) || "").trim();
  const why = String(searchParams.get(CHAT_FROM_RAIL_WHY_PARAM) || "").trim();
  const items = chatFromRailItems(searchParams);
  return buildRailChatPrompt({
    railTitle,
    items,
    focusTitle: focus,
    focusWhy: why,
  });
}

export function stripChatFromRailParam(searchParams) {
  const next = new URLSearchParams(searchParams);
  next.delete(CHAT_FROM_RAIL_PARAM);
  next.delete(CHAT_FROM_RAIL_TITLE_PARAM);
  next.delete(CHAT_FROM_RAIL_WHY_PARAM);
  next.delete(CHAT_FROM_RAIL_PACK_PARAM);
  next.delete(CHAT_FROM_RAIL_ID_PARAM);
  next.delete("rail_titles");
  next.delete(RECOMMEND_LIKE_PARAM);
  next.delete(RECOMMEND_LIKE_YEAR_PARAM);
  next.delete(RECOMMEND_LIKE_TYPE_PARAM);
  return next;
}

/** True when URL search asks to open the Watchlist panel. */
export function isWatchlistPanelRequest(searchParams) {
  if (!searchParams || typeof searchParams.get !== "function") return false;
  const value = String(searchParams.get(WATCHLIST_PANEL_PARAM) || "").toLowerCase();
  return value === "1" || value === "open" || value === "true";
}

/** True when URL search asks to open the rate flow. */
export function isRateFlowRequest(searchParams) {
  if (!searchParams || typeof searchParams.get !== "function") return false;
  const value = String(searchParams.get(RATE_FLOW_PARAM) || "").toLowerCase();
  return value === "1" || value === "open" || value === "true";
}

/** Return a copy of search params without the Watchlist panel flag. */
export function stripWatchlistPanelParam(searchParams) {
  const next = new URLSearchParams(searchParams);
  next.delete(WATCHLIST_PANEL_PARAM);
  return next;
}

/** Return a copy of search params without the rate-flow flag. */
export function stripRateFlowParam(searchParams) {
  const next = new URLSearchParams(searchParams);
  next.delete(RATE_FLOW_PARAM);
  return next;
}

/** Return a copy without the one-shot recommend-like chat seed. */
export function stripRecommendLikeParam(searchParams) {
  const next = new URLSearchParams(searchParams);
  next.delete(RECOMMEND_LIKE_PARAM);
  next.delete(RECOMMEND_LIKE_YEAR_PARAM);
  next.delete(RECOMMEND_LIKE_TYPE_PARAM);
  return next;
}

/**
 * Resolve a "back" destination from optional location state + fallback.
 * Prefer an explicit `from` path when it is an internal app route.
 */
export function resolveBackTarget(locationState, fallback = ROUTES.chat) {
  const from = locationState?.from;
  if (typeof from === "string" && from.startsWith("/") && !from.startsWith("//")) {
    return from;
  }
  return fallback || ROUTES.chat;
}

export function backLabelForPath(path, { defaultLabel = "Back" } = {}) {
  const normalized = String(path || "").split("?")[0];
  if (normalized === ROUTES.chat || normalized === "/" || normalized === "") {
    return "Back to chat";
  }
  if (normalized === ROUTES.search) return "Back to Search";
  if (normalized === ROUTES.inbox) return "Back to Inbox";
  if (normalized === ROUTES.myJourney) return "Back to My Journey";
  if (normalized === ROUTES.explore) return "Back to Explore";
  if (normalized === ROUTES.tags || normalized.startsWith(`${ROUTES.tags}/`)) {
    return "Back to tag search";
  }
  if (normalized === ROUTES.plotLab) return "Back to Plot Lab";
  if (normalized === ROUTES.libraryBrowse) return "Back to Explore";
  if (normalized === ROUTES.watchlist) return "Back to chat";
  if (normalized.startsWith("/explore/section/")) return "Back to Explore";
  if (normalized.startsWith("/tag/")) return "Back to tag";
  if (normalized.startsWith("/person/")) return "Back to person";
  if (normalized.startsWith("/title/")) return "Back to title";
  if (normalized.startsWith("/settings")) return "Back to settings";
  if (normalized.startsWith("/admin")) return "Back to admin";
  if (normalized === ROUTES.help) return "Back to Help";
  if (normalized === ROUTES.privacy) return "Back to Privacy";
  if (normalized === ROUTES.about) return "Back to About";
  return defaultLabel;
}

/**
 * Resolve title-detail back href + label from location state (full-page bookmarks).
 * Prefers an explicit `from` (chat, explore, search, …); otherwise `fallback`.
 */
export function resolveTitleBackNav(locationState, fallback = ROUTES.chat) {
  const to = resolveBackTarget(locationState, fallback);
  return { to, label: backLabelForPath(to) };
}

/** Build location state so a destination can return here. */
export function withReturnTo(pathname, search = "") {
  const from = `${pathname || ""}${search || ""}` || ROUTES.chat;
  return { from };
}

/**
 * Preserve an existing return target when hopping title → title; otherwise
 * record the current location as `from`.
 */
export function returnStateFromLocation(location) {
  const existing = location?.state?.from;
  if (typeof existing === "string" && existing.startsWith("/") && !existing.startsWith("//")) {
    return { from: existing };
  }
  return withReturnTo(location?.pathname || "", location?.search || "");
}

export function tagsSearchPath() {
  return ROUTES.tags;
}

export function plotLabPath() {
  return ROUTES.plotLab;
}

export function exploreHubPath() {
  return ROUTES.explore;
}
