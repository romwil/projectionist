/** Admin section destinations — desktop rail + adaptive AppNav on `/admin/*`. */

import { ROUTES } from "./backNav.js";

/**
 * Admin rail items. `kind: "heading"` groups dense destinations without adding
 * routes. Labels stay short so the rail stays scannable.
 */
export const ADMIN_NAV = [
  { kind: "heading", id: "heading-home", label: "Home" },
  { to: "/admin/overview", id: "overview", label: "Overview" },
  { to: "/admin/connections", id: "connections", label: "Connections" },
  { to: "/admin/libraries", id: "libraries", label: "Libraries" },
  { to: "/admin/sync", id: "sync", label: "Sync" },
  { kind: "heading", id: "heading-household", label: "Household" },
  { to: "/admin/persona", id: "persona", label: "Persona" },
  { to: "/admin/household", id: "household", label: "Members" },
  { to: "/admin/live-channels", id: "live-channels", label: "Live Channels" },
  { to: "/admin/seerr", id: "seerr", label: "Seerr" },
  { kind: "heading", id: "heading-ops", label: "Ops" },
  { to: "/admin/tasks", id: "tasks", label: "Tasks" },
  { to: "/admin/mail", id: "mail", label: "Mail" },
  { to: "/admin/access", id: "access", label: "Access" },
  { to: "/admin/dashboard", id: "dashboard", label: "Dashboard" },
  { to: "/admin/issues", id: "issues", label: "Issues", badge: "openIssues" },
  { to: "/admin/youth", id: "youth", label: "Youth" },
  { to: "/admin/advanced", id: "advanced", label: "Advanced" },
  { to: "/admin/logs", id: "logs", label: "Logs" },
];

/** Link items only (no group headings). */
export function adminNavLinks() {
  return ADMIN_NAV.filter((item) => item.kind !== "heading" && item.to);
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
      testId: `app-nav-admin-${item.id}`,
      kind: "admin",
      badge: item.badge || null,
    };
  });
}
