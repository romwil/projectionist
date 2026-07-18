/** Release notes helpers — What’s New gate + About panel. */

export const LAST_SEEN_VERSION_KEY = "curatorx.last_seen_version";
export const RELEASE_NOTES_URL = "/release-notes.json";

/**
 * Compare two semver strings (X.Y.Z). Non-semver segments sort as 0.
 * @returns {number} negative if a < b, 0 if equal, positive if a > b
 */
export function compareSemver(a, b) {
  const parse = (value) =>
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

export function getLastSeenVersion(storage = globalThis.localStorage) {
  try {
    return String(storage?.getItem?.(LAST_SEEN_VERSION_KEY) || "").trim() || null;
  } catch {
    return null;
  }
}

export function setLastSeenVersion(version, storage = globalThis.localStorage) {
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
export function shouldShowWhatsNew(runtimeVersion, lastSeenVersion) {
  const runtime = String(runtimeVersion || "").trim();
  if (!runtime) return false;
  const lastSeen = String(lastSeenVersion || "").trim();
  if (!lastSeen) return false;
  return compareSemver(runtime, lastSeen) > 0;
}

/**
 * Normalize /release-notes.json payload into a releases array.
 */
export function normalizeReleaseNotes(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload.filter((item) => item?.version);
  if (Array.isArray(payload.releases)) {
    return payload.releases.filter((item) => item?.version);
  }
  return [];
}

export function pickLatestRelease(releases) {
  const list = normalizeReleaseNotes(releases);
  if (!list.length) return null;
  return [...list].sort((a, b) => compareSemver(b.version, a.version))[0] || null;
}

export function findReleaseByVersion(releases, version) {
  const target = String(version || "").trim();
  if (!target) return null;
  return normalizeReleaseNotes(releases).find((item) => item.version === target) || null;
}

/** Strip light markdown markers for plain-text list rendering. */
export function plainChangelogText(value) {
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
