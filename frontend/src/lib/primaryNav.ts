/**
 * Shared primary destinations and role gating for Projectionist chrome.
 *
 * This is the single source of truth for peer destinations: `PrimaryTopbar`
 * renders `buildPrimaryNavItems` as icons and the AppNav drawer renders
 * `buildPrimaryDrawerItems` as labelled links, so role gating cannot drift
 * between the two surfaces.
 *
 * Icon order (L→R after hamburger + brand):
 * Search → Chat → Explore → Inbox → Admin → Settings
 *
 * BD-2: My Journey is not a primary peer — it is now the badges and
 * achievements section of the profile page (Settings → Profile). Legacy
 * `/my-journey` links redirect there rather than 404ing.
 */

import { ROUTES } from "./backNav.js";
import type {JsonObject, LibraryItem, JsParam} from "../api/types";

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
    icon: "chat",
    testId: "topbar-chat-link",
  },
  {
    id: "explore",
    to: ROUTES.explore,
    label: "Explore",
    youthLabel: "Browse",
    icon: "explore",
    testId: "topbar-explore-link",
  },
  {
    id: "live",
    to: ROUTES.live,
    label: "Live",
    icon: "live_tv",
    testId: "topbar-live-link",
    requiresLiveChannels: true,
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
    id: "settings",
    to: ROUTES.settings,
    label: "Settings",
    icon: "settings",
    testId: "topbar-settings-link",
  },
];

/**
 * Public peers painted on first load. They are route links, not session data.
 * Admin is omitted until auth settles: useAuthGate defaults isOwner=true.
 */
const PUBLIC_PRIMARY_IDS = ["search", "chat", "explore", "inbox", "settings"];

/**
 * Which primary toolbar peers a role may see.
 * Youth / member: no Admin.
 * Owner: full set, once auth has settled.
 *
 * A slow `/api/auth/me` must not hide Search, Chat, Explore, and the other
 * public peers. Live is included when this install already knows the feature
 * is on (HTML stamp or cache), without waiting on features/auth. Admin waits
 * on auth so a member never sees the owner icon while the session check is
 * in flight.
 */
export function primaryNavVisibleIds(
  {
  role = "owner",
  isOwner = false,
  isYouth = false,
  multiUserEnabled = true,
  authReady = true,
  liveChannelsReady = false,
}: JsParam = {},
) {
  const ids = [...PUBLIC_PRIMARY_IDS];
  if (liveChannelsReady) {
    // Live sits after Explore — living-room peer, not Admin utility.
    const exploreIdx = ids.indexOf("explore");
    ids.splice(exploreIdx + 1, 0, "live");
  }
  if (!authReady) {
    return ids;
  }
  const normalized = String(role || "owner").toLowerCase();
  const showAdmin = isOwner || (!multiUserEnabled && normalized === "owner");
  if (showAdmin && !isYouth) {
    // Insert Admin immediately before Settings.
    const settingsIdx = ids.indexOf("settings");
    ids.splice(settingsIdx, 0, "admin");
  }
  return ids;
}

/**
 * Build ordered primary nav items for the current viewer.
 * @returns {Array<object>}
 */
export function buildPrimaryNavItems(
  {
  role = "owner",
  isOwner = false,
  isYouth = false,
  multiUserEnabled = true,
  authReady = true,
  liveChannelsReady = false,
}: JsParam = {},
) {
  const visible = new Set(
    primaryNavVisibleIds({
      role,
      isOwner,
      isYouth,
      multiUserEnabled,
      authReady,
      liveChannelsReady,
    }),
  );
  return PRIMARY_NAV_ITEMS.filter((item) => visible.has(item.id)).map((item) => {
    let label = item.label;
    if (isYouth && item.youthLabel) label = item.youthLabel;
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
export function buildPrimaryDrawerItems(opts: JsParam = {}) {
  return buildPrimaryNavItems(opts).map((item) => ({
    id: item.id,
    to: item.to,
    label: item.label,
    icon: item.icon,
    kind: "primary",
    testId: `app-nav-${item.id}`,
  }));
}

/**
 * UX-014: phone/iPad bottom nav shows the same role-correct peers as the
 * topbar/drawer, but a bottom bar only has room for 5 — drop Live and Admin
 * first (both stay reachable from the hamburger drawer) rather than
 * cramming or wrapping.
 */
export function buildPrimaryBottomNavItems(opts: JsParam = {}) {
  const items = buildPrimaryNavItems(opts);
  if (items.length <= 5) return items;
  const droppable = new Set(["live", "admin"]);
  const trimmed = items.filter((item) => !droppable.has(item.id));
  if (trimmed.length <= 5) return trimmed;
  return trimmed.slice(0, 5);
}

/**
 * UX-014: the bottom nav is chrome, not content — hide it over the player
 * (`/watch/*`, `/live/watch`) and while the on-screen keyboard covers it
 * on iOS (composer focused), rather than fighting either for space.
 */
export function shouldHidePrimaryBottomNav({
  pathname = "",
  composerFocused = false,
  isIos = false,
}: JsParam = {}) {
  const path = String(pathname || "");
  if (path.startsWith("/watch/") || path === ROUTES.liveWatch) return true;
  if (isDoorPath(path)) return true;
  if (composerFocused && isIos) return true;
  return false;
}

/** UX-011: sign-in, join, and first-run setup are signed-out doors, never member chrome. */
const DOOR_PATHS = new Set(["/login", "/join", "/setup"]);

export function isDoorPath(pathname: JsParam) {
  const path = String(pathname || "").replace(/\/+$/, "") || "/";
  return DOOR_PATHS.has(path);
}

/** True when pathname is the chat workspace (including legacy `/`). */
export function isChatPath(pathname: JsParam) {
  const path = String(pathname || "");
  return path === ROUTES.chat || path === "/" || path === "";
}

/** Active match for a primary peer link. */
export function isPrimaryNavActive(item: LibraryItem | null | undefined, pathname: JsParam) {
  const path = String(pathname || "");
  if (item!.id === "chat") return isChatPath(path);
  if (item!.id === "explore") {
    return path === ROUTES.explore || path.startsWith(`${ROUTES.explore}/`);
  }
  if (item!.id === "live") {
    return path === ROUTES.live || path.startsWith(`${ROUTES.live}/`);
  }
  if (item!.id === "search") {
    return path === ROUTES.search || path.startsWith(`${ROUTES.search}?`);
  }
  if (item!.id === "inbox") return path === ROUTES.inbox;
  if (item!.id === "admin") return path === ROUTES.admin || path.startsWith(`${ROUTES.admin}/`);
  if (item!.id === "settings") {
    return path === ROUTES.settings || path.startsWith(`${ROUTES.settings}/`);
  }
  return path === item!.to || path.startsWith(`${item!.to}/`);
}
