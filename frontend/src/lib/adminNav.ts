/** Admin section destinations — desktop rail + adaptive AppNav on `/admin/*`. */

import { ROUTES } from "./backNav.js";
import type { JsParam } from "../api/types";

/**
 * Admin rail items. `kind: "heading"` groups dense destinations without adding
 * routes. Labels stay short so the rail stays scannable.
 */
export const ADMIN_NAV = [
  // Overview sits at the top of the rail without a visible section label.
  { kind: "heading", id: "heading-overview", label: "Overview", hideHeading: true },
  { to: "/admin/overview", id: "overview", label: "Overview" },
  { kind: "heading", id: "heading-setup", label: "Setup" },
  { to: "/admin/connections", id: "connections", label: "Connections" },
  { to: "/admin/libraries", id: "libraries", label: "Libraries" },
  { kind: "heading", id: "heading-members", label: "Household" },
  { to: "/admin/household", id: "household", label: "Members" },
  { to: "/admin/playback", id: "playback", label: "Playback" },
  { to: "/admin/access", id: "access", label: "Access" },
  { to: "/admin/youth", id: "youth", label: "Youth" },
  { kind: "heading", id: "heading-experience", label: "Experience" },
  { to: "/admin/live-channels", id: "live-channels", label: "Live" },
  { to: "/admin/lobby", id: "lobby", label: "Lobby" },
  { to: "/admin/holidays", id: "holidays", label: "Holidays" },
  { to: "/admin/seerr", id: "seerr", label: "Seerr" },
  { kind: "heading", id: "heading-health", label: "Health" },
  { to: "/admin/tasks", id: "tasks", label: "Tasks" },
  { to: "/admin/health", id: "health", label: "Health", badge: "openIssues" },
  { to: "/admin/taxonomy", id: "taxonomy", label: "Library knowledge" },
  { to: "/admin/logs", id: "logs", label: "Logs" },
  { kind: "heading", id: "heading-advanced", label: "Advanced" },
  { to: "/admin/persona", id: "persona", label: "Persona" },
  { to: "/admin/mail", id: "mail", label: "Mail" },
  { to: "/admin/newsletters", id: "newsletters", label: "Newsletters" },
  {
    to: "/admin/advanced",
    id: "advanced",
    label: "Advanced",
    subtitle: "Integrations & keys",
  },
];

/** Link ids for solo installs (`multi_user_enabled=false`), in rail order. */
export const SINGLE_USER_ADMIN_LINK_IDS = [
  "overview",
  "connections",
  "libraries",
  "playback",
  "lobby",
  "live-channels",
  "tasks",
  "logs",
  "persona",
  "advanced",
];

const SINGLE_USER_OVERVIEW_IDS = ["overview"];
const SINGLE_USER_SETUP_IDS = ["connections", "libraries"];
const SINGLE_USER_HOUSEHOLD_IDS = ["playback"];
const SINGLE_USER_EXPERIENCE_IDS = ["lobby", "live-channels"];
const SINGLE_USER_HEALTH_IDS = ["tasks", "logs"];
const SINGLE_USER_ADVANCED_IDS = ["persona", "advanced"];

/** Copy grouping Lobby + Live for living-room setup. */
export const ADMIN_EXPERIENCE_SUBTITLE =
  "On the wall — lobby kiosk & live TV. See Help → Living room.";

function adminItemById(id: string) {
  return ADMIN_NAV.find((item) => item.id === id);
}

function pickAdminItems(ids: JsParam) {
  return ids.map((id: JsParam) => adminItemById(id)).filter(Boolean);
}

/**
 * Solo-install admin rail — same groups as multi-user, minus member management
 * and the dense Health / Advanced destinations. Household keeps Playback,
 * because those controls apply to the whole install.
 * @param {{ seerrEnabled?: boolean }} [opts]
 */
function buildSingleUserAdminNav({ seerrEnabled = false }: JsParam = {}) {
  const experienceIds = [...SINGLE_USER_EXPERIENCE_IDS];
  if (seerrEnabled) experienceIds.push("seerr");

  return [
    { kind: "heading", id: "heading-overview", label: "Overview", hideHeading: true },
    ...pickAdminItems(SINGLE_USER_OVERVIEW_IDS),
    { kind: "heading", id: "heading-setup", label: "Setup" },
    ...pickAdminItems(SINGLE_USER_SETUP_IDS),
    { kind: "heading", id: "heading-household", label: "Household" },
    ...pickAdminItems(SINGLE_USER_HOUSEHOLD_IDS),
    {
      kind: "heading",
      id: "heading-experience",
      label: "Experience",
      subtitle: ADMIN_EXPERIENCE_SUBTITLE,
    },
    ...pickAdminItems(experienceIds),
    { kind: "heading", id: "heading-health", label: "Health" },
    ...pickAdminItems(SINGLE_USER_HEALTH_IDS),
    { kind: "heading", id: "heading-advanced", label: "Advanced" },
    ...pickAdminItems(SINGLE_USER_ADVANCED_IDS),
  ];
}

/**
 * Admin nav for the current install mode.
 * @param {{ multiUserEnabled?: boolean, seerrEnabled?: boolean }} [opts]
 */
export function resolveAdminNav({ multiUserEnabled = true, seerrEnabled = false }: JsParam = {}) {
  if (multiUserEnabled !== false) return ADMIN_NAV;
  return buildSingleUserAdminNav({ seerrEnabled });
}

/** Link items only (no group headings). */
export function adminNavLinks(opts: JsParam = {}) {
  return resolveAdminNav(opts).filter((item) => item.kind !== "heading" && item.to);
}

/**
 * Admin rail as ordered groups.
 * @param {{ multiUserEnabled?: boolean, seerrEnabled?: boolean }} [opts]
 * @returns {Array<{ id: string, label: string, subtitle?: string, hideHeading?: boolean, links: Array<object> }>}
 */
export function adminNavGroups(opts: JsParam = {}) {
  const groups: JsParam[] = [];
  let current: JsParam = null;
  for (const item of resolveAdminNav(opts)) {
    if (item.kind === "heading") {
      current = {
        id: item.id,
        label: item.label,
        subtitle: item.subtitle || null,
        hideHeading: item.hideHeading === true,
        links: [] as JsParam[],
      };
      groups.push(current);
      continue;
    }
    if (!current) continue;
    current.links.push(item);
  }
  return groups;
}

/** True when pathname is under `/admin`. */
export function isAdminPath(pathname: JsParam) {
  const path = String(pathname || "");
  return path === ROUTES.admin || path.startsWith(`${ROUTES.admin}/`);
}

/**
 * Admin section links shaped for the AppNav drawer (headings included).
 * @param {{ multiUserEnabled?: boolean, seerrEnabled?: boolean }} [opts]
 * @returns {Array<object>}
 */
export function buildAdminDrawerItems(opts: JsParam = {}) {
  return resolveAdminNav(opts).map((item) => {
    if (item.kind === "heading") {
      return {
        kind: "heading",
        id: `admin-${item.id}`,
        label: item.label,
        subtitle: item.subtitle || null,
        ...(item.hideHeading ? { hideHeading: true } : {}),
        testId: `app-nav-admin-${item.id}`,
      };
    }
    return {
      id: `admin-${item.id}`,
      to: item.to,
      label: item.label,
      subtitle: item.subtitle || null,
      testId: `app-nav-admin-${item.id}`,
      kind: "admin",
      badge: item.badge || null,
    };
  });
}
