/** Shared return-navigation helpers for browse / detail pages. */

export const ROUTES = {
  chat: "/",
  explore: "/explore",
  tags: "/explore/tags",
  plotLab: "/explore/plot-lab",
  libraryBrowse: "/explore/browse",
  watchlist: "/watchlist",
  library: "/library",
  /** Sync/token settings only — browse pins on /watchlist. */
  watchlistSettings: "/settings/watchlist",
  settings: "/settings",
  admin: "/admin",
  adminTasks: "/admin/tasks",
  adminDashboard: "/admin/dashboard",
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
 * Deep-link to chat with rail context (titles + optional persona why).
 * @param {{ railTitle?: string, railId?: string, items?: Array<{ title?: string, why?: string, year?: number }> }} rail
 * @param {{ title?: string, why?: string } | null} [focusItem]
 */
export function chatFromRailHref(rail, focusItem = null) {
  const params = new URLSearchParams();
  const railTitle = String(rail?.railTitle || rail?.title || "this rail").trim();
  params.set(CHAT_FROM_RAIL_PARAM, "1");
  params.set(CHAT_FROM_RAIL_TITLE_PARAM, railTitle.slice(0, 120));
  if (focusItem?.title) {
    params.set(RECOMMEND_LIKE_PARAM, String(focusItem.title).trim().slice(0, 120));
    if (focusItem.why) {
      params.set(CHAT_FROM_RAIL_WHY_PARAM, String(focusItem.why).trim().slice(0, 280));
    }
  } else {
    const titles = (rail?.items || [])
      .map((item) => String(item?.title || "").trim())
      .filter(Boolean)
      .slice(0, 8);
    if (titles.length) {
      params.set("rail_titles", titles.join("|").slice(0, 400));
    }
  }
  return `${ROUTES.chat}?${params.toString()}`;
}

/** Build the seeded chat prompt from a chat-from-rail URL. */
export function chatFromRailPrompt(searchParams) {
  if (!searchParams || typeof searchParams.get !== "function") return "";
  if (String(searchParams.get(CHAT_FROM_RAIL_PARAM) || "") !== "1") return "";
  const railTitle = String(searchParams.get(CHAT_FROM_RAIL_TITLE_PARAM) || "this rail").trim();
  const focus = String(searchParams.get(RECOMMEND_LIKE_PARAM) || "").trim();
  const why = String(searchParams.get(CHAT_FROM_RAIL_WHY_PARAM) || "").trim();
  if (focus) {
    const whyBit = why ? ` The curator said: "${why}"` : "";
    return `Let's talk about "${focus}" from my "${railTitle}" picks.${whyBit} What should I know, and what else fits that vibe in my library?`;
  }
  const titles = String(searchParams.get("rail_titles") || "")
    .split("|")
    .map((t) => t.trim())
    .filter(Boolean);
  const list = titles.length ? ` Titles: ${titles.map((t) => `"${t}"`).join(", ")}.` : "";
  return `I want to chat about my "${railTitle}" picks.${list} Help me choose what to watch and why.`;
}

export function stripChatFromRailParam(searchParams) {
  const next = new URLSearchParams(searchParams);
  next.delete(CHAT_FROM_RAIL_PARAM);
  next.delete(CHAT_FROM_RAIL_TITLE_PARAM);
  next.delete(CHAT_FROM_RAIL_WHY_PARAM);
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
  if (normalized === ROUTES.chat || normalized === "") return "Back to chat";
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

/** Build location state so a destination can return here. */
export function withReturnTo(pathname, search = "") {
  const from = `${pathname || ""}${search || ""}` || ROUTES.explore;
  return { from };
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
