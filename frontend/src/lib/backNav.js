/** Shared return-navigation helpers for browse / detail pages. */

export const ROUTES = {
  chat: "/",
  explore: "/explore",
  tags: "/explore/tags",
  plotLab: "/explore/plot-lab",
  watchlistSettings: "/settings/watchlist",
  settings: "/settings",
  admin: "/admin",
  about: "/about",
};

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
