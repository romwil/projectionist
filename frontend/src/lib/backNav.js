/** Shared return-navigation helpers for browse / detail pages. */

export const ROUTES = {
  chat: "/",
  explore: "/explore",
  tags: "/explore/tags",
  plotLab: "/explore/plot-lab",
  /** Sync/token settings only — pin list lives in the chat Watchlist panel. */
  watchlistSettings: "/settings/watchlist",
  settings: "/settings",
  admin: "/admin",
  about: "/about",
};

/** Query flag that opens the chat Watchlist panel when landing on `/`. */
export const WATCHLIST_PANEL_PARAM = "watchlist";

/** Query flag that opens the /rate review batch flow in chat. */
export const RATE_FLOW_PARAM = "rate";

/** Deep-link to chat with the Watchlist panel open. */
export function watchlistPanelHref() {
  return `${ROUTES.chat}?${WATCHLIST_PANEL_PARAM}=1`;
}

/** Deep-link to chat that triggers the rate / review batch flow. */
export function rateFlowHref() {
  return `${ROUTES.chat}?${RATE_FLOW_PARAM}=1`;
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
  if (normalized.startsWith("/explore/section/")) return "Back to Explore";
  if (normalized.startsWith("/tag/")) return "Back to tag";
  if (normalized.startsWith("/person/")) return "Back to person";
  if (normalized.startsWith("/title/")) return "Back to title";
  if (normalized.startsWith("/settings")) return "Back to settings";
  if (normalized.startsWith("/admin")) return "Back to admin";
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
