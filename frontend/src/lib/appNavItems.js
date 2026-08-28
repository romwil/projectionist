/**
 * AppNav (hamburger drawer) destinations.
 *
 * The drawer mirrors the toolbar: a **Navigate** block of the same role-gated
 * primary peers `PrimaryTopbar` shows, then a **More** block of secondary
 * destinations that never earn a toolbar icon. Both blocks come from one model
 * (`primaryNav.js` + the constants below) so role gating cannot drift.
 */

import { buildAdminDrawerItems, isAdminPath } from "./adminNav.js";
import { ROUTES } from "./backNav.js";
import { libraryHubPath } from "./libraryTabs.js";
import { buildPrimaryDrawerItems } from "./primaryNav.js";

/** Secondary destinations for adults — no toolbar icon of their own. */
export const APP_NAV_CORE_ITEMS = [
  {
    id: "related-titles",
    to: ROUTES.relatedTitles,
    label: "Related titles",
    testId: "app-nav-related-titles",
  },
  { id: "tags", to: ROUTES.tags, label: "Tags", testId: "app-nav-tags" },
  { id: "library", to: ROUTES.library, label: "Library", testId: "app-nav-library" },
];

export const YOUTH_NAV_ITEMS = [
  {
    id: "watchlist",
    to: libraryHubPath("watchlist"),
    label: "My list",
    testId: "app-nav-watchlist",
  },
];

/** Secondary ("More") destinations for the current role. */
function secondaryNavItems({ isYouth, role }) {
  void role;
  if (isYouth) {
    return [
      ...YOUTH_NAV_ITEMS,
      { id: "help", to: ROUTES.help, label: "Help", testId: "app-nav-help" },
    ];
  }
  return [
    ...APP_NAV_CORE_ITEMS,
    { id: "help", to: ROUTES.help, label: "Help", testId: "app-nav-help" },
    { id: "privacy", to: ROUTES.privacy, label: "Privacy", testId: "app-nav-privacy" },
    { id: "about", to: ROUTES.about, label: "About", testId: "app-nav-about" },
  ];
}

/**
 * Build the ordered AppNav link list for the current role / youth mode.
 *
 * Blocks, in order: **Navigate** (the toolbar's peers for this role, labelled),
 * **Admin** (owner section links, only while on `/admin/*` — added alongside
 * Navigate, never instead of it), then **More** (secondary destinations).
 * My Journey lives in Navigate only; it is never repeated under More.
 * @param {{ isOwner?: boolean, showSettings?: boolean, isYouth?: boolean, role?: string, pathname?: string, multiUserEnabled?: boolean, authReady?: boolean, liveChannelsReady?: boolean }} [opts]
 */
export function buildAppNavItems({
  isOwner = false,
  showSettings = true,
  isYouth = false,
  role = "owner",
  pathname = "",
  multiUserEnabled = true,
  authReady = true,
  liveChannelsReady = false,
} = {}) {
  void showSettings;
  const primary = buildPrimaryDrawerItems({
    role,
    isOwner,
    isYouth,
    multiUserEnabled,
    authReady,
    liveChannelsReady,
  });
  const secondary = secondaryNavItems({ isYouth, role });

  const items = [];
  if (primary.length > 0) {
    items.push({ kind: "heading", id: "heading-navigate", label: "Navigate" });
    items.push(...primary);
  }
  if (isOwner && authReady && isAdminPath(pathname)) {
    items.push({ kind: "heading", id: "heading-admin", label: "Admin" });
    items.push(...buildAdminDrawerItems());
  }
  if (secondary.length > 0) {
    items.push({ kind: "heading", id: "heading-more", label: "More" });
    items.push(...secondary);
  }
  return items;
}
