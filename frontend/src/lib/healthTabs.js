/** Admin → Health tab routing (`/admin/health?tab=`). */

export const HEALTH_TABS = [
  { id: "sync", label: "Sync health", testId: "health-tab-sync" },
  { id: "usage", label: "Usage / LLM spend", testId: "health-tab-usage" },
  { id: "issues", label: "Issues / media", testId: "health-tab-issues" },
];

const LEGACY_HEALTH_PATHS = {
  dashboard: "sync",
  usage: "usage",
  issues: "issues",
};

/** Resolve a tab id from `?tab=` (defaults to sync health / dashboard). */
export function resolveHealthTab(raw) {
  const tab = String(raw || "")
    .trim()
    .toLowerCase();
  if (HEALTH_TABS.some((entry) => entry.id === tab)) return tab;
  return "sync";
}

/** Canonical admin Health href for a tab. */
export function healthTabHref(tab) {
  const resolved = resolveHealthTab(tab);
  return resolved === "sync" ? "/admin/health" : `/admin/health?tab=${resolved}`;
}

/** Map legacy `/admin/{dashboard|usage|issues}` paths to a Health tab id. */
export function legacyHealthTabFromPath(pathname) {
  const segment = String(pathname || "")
    .split("/")
    .filter(Boolean)
    .pop();
  return LEGACY_HEALTH_PATHS[segment] || null;
}
