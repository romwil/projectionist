/** Admin section destinations — desktop rail + adaptive AppNav on `/admin/*`. */

import { ROUTES } from "./backNav.js";

export const ADMIN_NAV = [
  { to: "/admin/overview", id: "overview", label: "Overview" },
  { to: "/admin/connections", id: "connections", label: "Connections" },
  { to: "/admin/libraries", id: "libraries", label: "Libraries" },
  { to: "/admin/sync", id: "sync", label: "Sync" },
  { to: "/admin/tasks", id: "tasks", label: "Scheduled Tasks" },
  { to: "/admin/persona", id: "persona", label: "Persona" },
  { to: "/admin/household", id: "household", label: "Household" },
  { to: "/admin/seerr", id: "seerr", label: "Seerr" },
  { to: "/admin/mail", id: "mail", label: "Mail & alerts" },
  { to: "/admin/access", id: "access", label: "Access requests" },
  { to: "/admin/advanced", id: "advanced", label: "Advanced" },
  { to: "/admin/dashboard", id: "dashboard", label: "Dashboard" },
  { to: "/admin/issues", id: "issues", label: "Issues", badge: "openIssues" },
  { to: "/admin/youth", id: "youth", label: "Youth review" },
];

/** True when pathname is under `/admin`. */
export function isAdminPath(pathname) {
  const path = String(pathname || "");
  return path === ROUTES.admin || path.startsWith(`${ROUTES.admin}/`);
}

/**
 * Admin section links shaped for the AppNav drawer.
 * @returns {Array<{ id: string, to: string, label: string, testId: string, kind: string, badge: string|null }>}
 */
export function buildAdminDrawerItems() {
  return ADMIN_NAV.map((item) => ({
    id: `admin-${item.id}`,
    to: item.to,
    label: item.label,
    testId: `app-nav-admin-${item.id}`,
    kind: "admin",
    badge: item.badge || null,
  }));
}
