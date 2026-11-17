/**
 * Libraries hub — sticky subnav tabs + attention-strip routing.
 * Keeps panel ids stable for scroll targets and Playwright.
 */

import { radarrRegisterHasPathConflicts } from "./rematchStudio.js";
import type { JsParam } from "../api/types";

export const LIBRARIES_HUB_TABS = [
  { id: "sync", label: "Sync", panelId: "libraries-panel-sync" },
  { id: "arr", label: "Arr jobs", panelId: "libraries-panel-arr" },
  { id: "repair", label: "Repair", panelId: "libraries-panel-repair" },
  { id: "rematch", label: "Rematch", panelId: "libraries-panel-rematch" },
  { id: "identify", label: "Identify", panelId: "libraries-panel-identify" },
  { id: "plex", label: "Plex", panelId: "libraries-panel-plex" },
] as const;

export type LibrariesHubTabId = (typeof LIBRARIES_HUB_TABS)[number]["id"];

export type LibrariesAttentionItem = {
  id: string;
  title: string;
  detail: string;
  severity: "warning" | "danger" | "info";
  tabId: LibrariesHubTabId;
  panelId: string;
  ctaLabel: string;
};

const STALE_SYNC_MS = 7 * 24 * 60 * 60 * 1000;

function panelForTab(tabId: LibrariesHubTabId) {
  return LIBRARIES_HUB_TABS.find((tab) => tab.id === tabId)?.panelId || "libraries-panel-sync";
}

function parseSyncTime(lastSync: unknown): number | null {
  if (!lastSync) return null;
  const ms = Date.parse(String(lastSync));
  return Number.isFinite(ms) ? ms : null;
}

/** Count open path conflicts in a Radarr register job snapshot. */
export function countPathConflicts(radarrRegister: JsParam) {
  const items = Array.isArray(radarrRegister?.items) ? radarrRegister.items : [];
  return items.filter((row: JsParam) => String(row?.outcome || "").toLowerCase() === "path_conflict")
    .length;
}

/** True when library sync never ran or last sync is older than a week. */
export function isSyncStale(libraryStats: JsParam, nowMs = Date.now()) {
  if (!libraryStats) return true;
  const ms = parseSyncTime(libraryStats.last_sync);
  if (ms == null) return true;
  return nowMs - ms > STALE_SYNC_MS;
}

/**
 * Build the Libraries attention strip from live job / sync snapshots.
 * @param {{ libraryStats?: object, radarrRegister?: object, sonarrMissing?: object, activeSyncJob?: object, nowMs?: number }} input
 */
export function buildLibrariesAttention({
  libraryStats = null,
  radarrRegister = null,
  sonarrMissing = null,
  activeSyncJob = null,
  nowMs = Date.now(),
}: JsParam = {}): LibrariesAttentionItem[] {
  const items: LibrariesAttentionItem[] = [];

  const pathConflicts = countPathConflicts(radarrRegister);
  if (pathConflicts > 0 || radarrRegisterHasPathConflicts(radarrRegister)) {
    const n = pathConflicts || 1;
    items.push({
      id: "path-conflicts",
      title: n === 1 ? "Path conflict" : `${n} path conflicts`,
      detail: "Radarr already owns a folder under a different identity — re-check or choose identity.",
      severity: "danger",
      tabId: "repair",
      panelId: panelForTab("repair"),
      ctaLabel: "Open Repair",
    });
  }

  const syncFailed =
    String(activeSyncJob?.status || "").toLowerCase() === "failed" ||
    String(activeSyncJob?.state || "").toLowerCase() === "failed";
  if (syncFailed) {
    items.push({
      id: "sync-failed",
      title: "Library sync failed",
      detail: String(activeSyncJob?.error || activeSyncJob?.message || "Last sync did not finish."),
      severity: "danger",
      tabId: "sync",
      panelId: panelForTab("sync"),
      ctaLabel: "Open Sync",
    });
  } else if (isSyncStale(libraryStats, nowMs)) {
    const never = !libraryStats?.last_sync;
    items.push({
      id: "stale-sync",
      title: never ? "Library not synced yet" : "Library sync is stale",
      detail: never
        ? "Run Sync library after Plex is connected so titles show up."
        : "Last sync was more than a week ago — refresh when the library has changed.",
      severity: "warning",
      tabId: "sync",
      panelId: panelForTab("sync"),
      ctaLabel: "Open Sync",
    });
  }

  const sonarrFailed = Number(sonarrMissing?.execution?.failed) > 0 || Boolean(sonarrMissing?.error);
  if (sonarrFailed) {
    items.push({
      id: "sonarr-failures",
      title: "Sonarr search had failures",
      detail: String(
        sonarrMissing?.execution?.last_error ||
          sonarrMissing?.error ||
          "Some EpisodeSearch commands failed — check Arr jobs / Repair.",
      ),
      severity: "warning",
      tabId: "arr",
      panelId: panelForTab("arr"),
      ctaLabel: "Open Arr jobs",
    });
  }

  return items;
}

/** Resolve a hash / tab query to a hub tab id. */
export function resolveLibrariesHubTab(raw: unknown): LibrariesHubTabId {
  const value = String(raw || "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase();
  if (!value) return "sync";
  const byId = LIBRARIES_HUB_TABS.find((tab) => tab.id === value || tab.panelId === value);
  if (byId) return byId.id;
  if (value === "library-sync" || value === "sync-library") return "sync";
  if (value === "rematch-studio") return "rematch";
  if (value === "episode-investigate" || value === "investigate") return "identify";
  if (value.includes("repair") || value.includes("path")) return "repair";
  if (value.includes("radarr") || value.includes("sonarr") || value === "arr-jobs") return "arr";
  if (value.includes("plex")) return "plex";
  return "sync";
}
