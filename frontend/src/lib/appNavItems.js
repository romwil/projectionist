/** Primary AppNav destinations — shared by AppNav drawer and unit tests. */

import { ROUTES } from "./backNav.js";

export const APP_NAV_CORE_ITEMS = [
  { id: "chat", to: ROUTES.chat, label: "Chat", testId: "app-nav-chat" },
  { id: "explore", to: ROUTES.explore, label: "Explore", testId: "app-nav-explore" },
  { id: "plot-lab", to: ROUTES.plotLab, label: "Plot Lab", testId: "app-nav-plot-lab" },
  { id: "tags", to: ROUTES.tags, label: "Tags", testId: "app-nav-tags" },
  { id: "watchlist", kind: "watchlist", label: "Watchlist", testId: "app-nav-watchlist" },
];

/**
 * Build the ordered AppNav link list for the current role.
 * @param {{ isOwner?: boolean, showSettings?: boolean }} [opts]
 */
export function buildAppNavItems({ isOwner = false, showSettings = true } = {}) {
  const items = [...APP_NAV_CORE_ITEMS];
  if (showSettings) {
    items.push({ id: "settings", to: ROUTES.settings, label: "Settings", testId: "app-nav-settings" });
  }
  if (isOwner) {
    items.push({ id: "admin", to: ROUTES.admin, label: "Admin", testId: "app-nav-admin" });
  }
  items.push({ id: "help", to: ROUTES.help, label: "Help", testId: "app-nav-help" });
  items.push({ id: "privacy", to: ROUTES.privacy, label: "Privacy", testId: "app-nav-privacy" });
  items.push({ id: "about", to: ROUTES.about, label: "About", testId: "app-nav-about" });
  return items;
}
