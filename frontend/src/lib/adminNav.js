/** Admin section destinations — desktop rail + adaptive AppNav on `/admin/*`. */

import { ROUTES } from "./backNav.js";

/**
 * Admin rail items. `kind: "heading"` groups dense destinations without adding
 * routes. Labels stay short so the rail stays scannable.
 */
export const ADMIN_NAV = [
  { kind: "heading", id: "heading-setup", label: "Setup" },
  { to: "/admin/overview", id: "overview", label: "Overview" },
  { to: "/admin/connections", id: "connections", label: "Connections" },
  { to: "/admin/libraries", id: "libraries", label: "Libraries" },
  { to: "/admin/persona", id: "persona", label: "Persona" },
  { to: "/admin/household", id: "household", label: "Members" },
  { kind: "heading", id: "heading-experience", label: "Experience" },
  { to: "/admin/live-channels", id: "live-channels", label: "Live Channels" },
  { to: "/admin/lobby", id: "lobby", label: "Lobby" },
  { to: "/admin/holidays", id: "holidays", label: "Holidays" },
  { to: "/admin/seerr", id: "seerr", label: "Seerr" },
  { kind: "heading", id: "heading-platform", label: "Platform" },
  { to: "/admin/tasks", id: "tasks", label: "Tasks" },
  { to: "/admin/taxonomy", id: "taxonomy", label: "Library knowledge" },
  { to: "/admin/health", id: "health", label: "Health", badge: "openIssues" },
  { kind: "heading", id: "heading-comms", label: "Communications" },
  { to: "/admin/mail", id: "mail", label: "Mail" },
  { to: "/admin/newsletters", id: "newsletters", label: "Newsletters" },
  { kind: "heading", id: "heading-system", label: "System" },
  { to: "/admin/access", id: "access", label: "Access" },
  { to: "/admin/youth", id: "youth", label: "Youth" },
  {
    to: "/admin/advanced",
    id: "advanced",
    label: "Advanced",
    subtitle: "Integrations & keys",
  },
  { to: "/admin/logs", id: "logs", label: "Logs" },
];

/** Link items only (no group headings). */
export function adminNavLinks() {
  return ADMIN_NAV.filter((item) => item.kind !== "heading" && item.to);
}

/**
 * Admin rail as ordered groups (Setup / Experience / Platform / Comms / System).
 * Headings stay section chrome; links keep the same destinations.
 * @returns {Array<{ id: string, label: string, links: Array<object> }>}
 */
export function adminNavGroups() {
  const groups = [];
  let current = null;
  for (const item of ADMIN_NAV) {
    if (item.kind === "heading") {
      current = { id: item.id, label: item.label, links: [] };
      groups.push(current);
      continue;
    }
    if (!current) continue;
    current.links.push(item);
  }
  return groups;
}

/** True when pathname is under `/admin`. */
export function isAdminPath(pathname) {
  const path = String(pathname || "");
  return path === ROUTES.admin || path.startsWith(`${ROUTES.admin}/`);
}

/**
 * Admin section links shaped for the AppNav drawer (headings included).
 * @returns {Array<object>}
 */
export function buildAdminDrawerItems() {
  return ADMIN_NAV.map((item) => {
    if (item.kind === "heading") {
      return {
        kind: "heading",
        id: `admin-${item.id}`,
        label: item.label,
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
