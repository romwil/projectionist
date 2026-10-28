import type {JsonObject, JsParam} from "../api/types";
/** Release notes helpers — What’s New gate + About panel. */

export const LAST_SEEN_VERSION_KEY = "projectionist.last_seen_version";
export const RELEASE_NOTES_URL = "/release-notes.json";

/**
 * Compare two semver strings (X.Y.Z). Non-semver segments sort as 0.
 * @returns {number} negative if a < b, 0 if equal, positive if a > b
 */
export function compareSemver(a: JsParam, b: unknown) {
  const parse = (value: JsParam) =>
    String(value || "")
      .trim()
      .replace(/^v/i, "")
      .split(/[.+-]/)
      .slice(0, 3)
      .map((part) => {
        const n = Number.parseInt(part, 10);
        return Number.isFinite(n) ? n : 0;
      });
  const left = parse(a);
  const right = parse(b);
  while (left.length < 3) left.push(0);
  while (right.length < 3) right.push(0);
  for (let i = 0; i < 3; i += 1) {
    if (left[i] !== right[i]) return left[i] - right[i];
  }
  return 0;
}

export function getLastSeenVersion(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    return String(storage?.getItem?.(LAST_SEEN_VERSION_KEY) || "").trim() || null;
  } catch {
    return null;
  }
}

export function setLastSeenVersion(version: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const normalized = String(version || "").trim();
  if (!normalized) return;
  try {
    storage?.setItem?.(LAST_SEEN_VERSION_KEY, normalized);
  } catch {
    // localStorage unavailable
  }
}

/**
 * Show What’s New after an upgrade (runtime newer than last seen).
 * First visit with no stored version: bootstrap silently (no modal).
 */
export function shouldShowWhatsNew(runtimeVersion: JsParam, lastSeenVersion: JsParam) {
  const runtime = String(runtimeVersion || "").trim();
  if (!runtime) return false;
  const lastSeen = String(lastSeenVersion || "").trim();
  if (!lastSeen) return false;
  return compareSemver(runtime, lastSeen) > 0;
}

/**
 * Normalize /release-notes.json payload into a releases array.
 */
export function normalizeReleaseNotes(payload: JsParam) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload.filter((item) => item?.version);
  if (Array.isArray(payload.releases)) {
    return payload.releases.filter((item: JsParam) => item?.version);
  }
  return [];
}

export function pickLatestRelease(releases: JsParam) {
  const list = normalizeReleaseNotes(releases);
  if (!list.length) return null;
  return [...list].sort((a, b) => compareSemver(b.version, a.version))[0] || null;
}

export function findReleaseByVersion(releases: JsParam, version: JsParam) {
  const target = String(version || "").trim();
  if (!target) return null;
  return normalizeReleaseNotes(releases).find((item: JsParam) => item.version === target) || null;
}

/** Max version chips in the About jump rail before switching to a picker. */
export const RELEASE_JUMP_RECENT_LIMIT = 10;

/**
 * Allocate release-version jump UI for long histories.
 * Short lists stay a chip rail; long lists get a compact picker + recent chips
 * so About never becomes a wall of every patch number.
 *
 * @param {unknown} releases
 * @param {{ recentLimit?: number }} [options]
 * @returns {{ mode: "chips" | "picker", recent: string[], all: string[] }}
 */
export function allocateReleaseVersionJumps(releases: JsParam, { recentLimit = RELEASE_JUMP_RECENT_LIMIT }: JsParam = {}) {
  const versions = normalizeReleaseNotes(releases)
    .map((item: JsParam) => String(item.version || "").trim())
    .filter(Boolean);
  const limit = Math.max(1, Number(recentLimit) || RELEASE_JUMP_RECENT_LIMIT);
  if (versions.length <= limit) {
    return { mode: "chips", recent: versions, all: versions };
  }
  return {
    mode: "picker",
    recent: versions.slice(0, limit),
    all: versions,
  };
}

/** Strip light markdown markers for plain-text list rendering. */
export function plainChangelogText(value: unknown) {
  return String(value || "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

export async function fetchReleaseNotes(fetchImpl = globalThis.fetch) {
  const response = await fetchImpl(RELEASE_NOTES_URL, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`Failed to load release notes (${response.status})`);
  }
  const contentType = String(response.headers?.get?.("content-type") || "").toLowerCase();
  // FastAPI SPA shells must not be mistaken for JSON when the static file is missing.
  if (contentType.includes("text/html")) {
    throw new Error("Failed to load release notes (HTML response)");
  }
  return response.json();
}
