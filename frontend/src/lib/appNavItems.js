/** Secondary AppNav destinations — drawer only; peers live in PrimaryTopbar. */

import { ROUTES } from "./backNav.js";

export const APP_NAV_CORE_ITEMS = [
  { id: "plot-lab", to: ROUTES.plotLab, label: "Plot Lab", testId: "app-nav-plot-lab" },
  { id: "tags", to: ROUTES.tags, label: "Tags", testId: "app-nav-tags" },
  { id: "watchlist", kind: "watchlist", label: "Watchlist", testId: "app-nav-watchlist" },
  { id: "library", to: ROUTES.library, label: "Library", testId: "app-nav-library" },
  {
    id: "my-journey",
    to: ROUTES.myJourney,
    label: "My Journey",
    testId: "app-nav-my-journey",
  },
];

export const YOUTH_NAV_ITEMS = [
  { id: "watchlist", kind: "watchlist", label: "My list", testId: "app-nav-watchlist" },
  {
    id: "my-journey",
    to: ROUTES.myJourney,
    label: "My Journey",
    testId: "app-nav-my-journey",
  },
];

export const GUEST_NAV_ITEMS = [
  { id: "tour", to: ROUTES.tour, label: "What's great", testId: "app-nav-tour" },
  { id: "collections", to: "/collections", label: "Collections", testId: "app-nav-collections" },
];

/**
 * Build the ordered AppNav link list for the current role / youth mode.
 * Primary peers (Search/Chat/Explore/Inbox/Admin/My Journey/Settings) live in the toolbar.
 * @param {{ isOwner?: boolean, showSettings?: boolean, isYouth?: boolean, role?: string }} [opts]
 */
export function buildAppNavItems({
  isOwner = false,
  showSettings = true,
  isYouth = false,
  role = "owner",
} = {}) {
  void isOwner;
  void showSettings;
  if (role === "guest") {
    const items = [...GUEST_NAV_ITEMS];
    items.push({ id: "help", to: ROUTES.help, label: "Help", testId: "app-nav-help" });
    items.push({ id: "about", to: ROUTES.about, label: "About", testId: "app-nav-about" });
    return items;
  }
  if (isYouth) {
    const items = [...YOUTH_NAV_ITEMS];
    items.push({ id: "help", to: ROUTES.help, label: "Help", testId: "app-nav-help" });
    return items;
  }
  const items = [...APP_NAV_CORE_ITEMS];
  items.push({ id: "help", to: ROUTES.help, label: "Help", testId: "app-nav-help" });
  items.push({ id: "privacy", to: ROUTES.privacy, label: "Privacy", testId: "app-nav-privacy" });
  items.push({ id: "about", to: ROUTES.about, label: "About", testId: "app-nav-about" });
  return items;
}
