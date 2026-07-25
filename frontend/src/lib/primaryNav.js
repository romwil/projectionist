/**
 * Shared primary destinations and role gating for CuratorX chrome.
 *
 * This is the single source of truth for peer destinations: `PrimaryTopbar`
 * renders `buildPrimaryNavItems` as icons and the AppNav drawer renders
 * `buildPrimaryDrawerItems` as labelled links, so role gating cannot drift
 * between the two surfaces.
 *
 * Icon order (L→R after hamburger + brand):
 * Search → Chat → Explore → Inbox → Admin → My Journey → Settings
 * (My Journey sits immediately left of Settings.)
 */

import { ROUTES } from "./backNav.js";

/** Stable peer destinations for the shared PrimaryTopbar. */
export const PRIMARY_NAV_ITEMS = [
  {
    id: "search",
    to: ROUTES.search,
    label: "Search",
    icon: "search",
    testId: "topbar-search-link",
  },
  {
    id: "chat",
    to: ROUTES.chat,
    label: "Chat",
    youthLabel: "Ask",
    guestLabel: "Ask",
    icon: "chat",
    testId: "topbar-chat-link",
  },
  {
    id: "explore",
    to: ROUTES.explore,
    label: "Explore",
    youthLabel: "Browse",
    guestLabel: "Browse",
    icon: "explore",
    testId: "topbar-explore-link",
  },
  {
    id: "inbox",
    to: ROUTES.inbox,
    label: "Inbox",
    icon: "notifications",
    testId: "topbar-inbox-button",
    kind: "inbox",
  },
  {
    id: "admin",
    to: ROUTES.admin,
    label: "Admin",
    icon: "admin_panel_settings",
    testId: "topbar-admin-link",
    ownerOnly: true,
  },
  {
    id: "my-journey",
    to: ROUTES.myJourney,
    label: "My Journey",
    icon: "route",
    testId: "topbar-my-journey-link",
  },
  {
    id: "settings",
    to: ROUTES.settings,
    label: "Settings",
    icon: "settings",
    testId: "topbar-settings-link",
  },
];

/**
 * Which primary toolbar peers a role may see.
 * Guest: Search, Chat, Explore only.
 * Youth / member: no Admin.
 * Owner: full set.
 *
 * When `authReady` is false (useAuthGate still settling; defaults isOwner=true),
 * return no peers — never failure-open Admin for members.
 */
export function primaryNavVisibleIds({
  role = "owner",
  isOwner = false,
  isYouth = false,
  multiUserEnabled = true,
  authReady = true,
} = {}) {
  if (!authReady) {
    return [];
  }
  const normalized = String(role || "owner").toLowerCase();
  if (normalized === "guest") {
    return ["search", "chat", "explore"];
  }
  const ids = ["search", "chat", "explore", "inbox", "my-journey", "settings"];
  const showAdmin = isOwner || (!multiUserEnabled && normalized === "owner");
  if (showAdmin && !isYouth) {
    // Insert Admin immediately before My Journey (left of Settings cluster).
    const journeyIdx = ids.indexOf("my-journey");
    ids.splice(journeyIdx, 0, "admin");
  }
  return ids;
}

/**
 * Build ordered primary nav items for the current viewer.
 * @returns {Array<object>}
 */
export function buildPrimaryNavItems({
  role = "owner",
  isOwner = false,
  isYouth = false,
  multiUserEnabled = true,
  authReady = true,
} = {}) {
  const visible = new Set(
    primaryNavVisibleIds({ role, isOwner, isYouth, multiUserEnabled, authReady }),
  );
  return PRIMARY_NAV_ITEMS.filter((item) => visible.has(item.id)).map((item) => {
    let label = item.label;
    if (isYouth && item.youthLabel) label = item.youthLabel;
    if (String(role).toLowerCase() === "guest" && item.guestLabel) label = item.guestLabel;
    return { ...item, label };
  });
}

/**
 * The same peers, shaped for the AppNav drawer: labelled links with
 * `app-nav-*` test ids instead of toolbar icons. Role gating comes from
 * `buildPrimaryNavItems`, so the drawer can never show a peer the toolbar
 * hides (or miss one it shows).
 * @returns {Array<object>}
 */
export function buildPrimaryDrawerItems(opts = {}) {
  return buildPrimaryNavItems(opts).map((item) => ({
    id: item.id,
    to: item.to,
    label: item.label,
    icon: item.icon,
    kind: "primary",
    testId: `app-nav-${item.id}`,
  }));
}

/** True when pathname is the chat workspace (including legacy `/`). */
export function isChatPath(pathname) {
  const path = String(pathname || "");
  return path === ROUTES.chat || path === "/" || path === "";
}

/** Active match for a primary peer link. */
export function isPrimaryNavActive(item, pathname) {
  const path = String(pathname || "");
  if (item.id === "chat") return isChatPath(path);
  if (item.id === "explore") {
    return path === ROUTES.explore || path.startsWith(`${ROUTES.explore}/`);
  }
  if (item.id === "search") {
    return path === ROUTES.search || path.startsWith(`${ROUTES.search}?`);
  }
  if (item.id === "my-journey") {
    return path === ROUTES.myJourney || path.startsWith(`${ROUTES.myJourney}/`);
  }
  if (item.id === "inbox") return path === ROUTES.inbox;
  if (item.id === "admin") return path === ROUTES.admin || path.startsWith(`${ROUTES.admin}/`);
  if (item.id === "settings") {
    return path === ROUTES.settings || path.startsWith(`${ROUTES.settings}/`);
  }
  return path === item.to || path.startsWith(`${item.to}/`);
}
