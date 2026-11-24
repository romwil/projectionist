/** Old Profile anchors that opened household-wide playback controls. */

export const HOUSEHOLD_PLAYBACK_PATH = "/admin/playback";

const PROFILE_PATHS = new Set(["/settings/profile"]);

const PROFILE_ROUTES = new Set(["/settings/playback", "/settings/profile/playback"]);

/** Hash id → admin destination. `#playback` opens the section itself. */
const PROFILE_HASHES: Record<string, string> = {
  playback: HOUSEHOLD_PLAYBACK_PATH,
  "play-through": `${HOUSEHOLD_PLAYBACK_PATH}#play-through-projectionist`,
  "play-through-projectionist": `${HOUSEHOLD_PLAYBACK_PATH}#play-through-projectionist`,
  away: `${HOUSEHOLD_PLAYBACK_PATH}#away-address`,
  "away-address": `${HOUSEHOLD_PLAYBACK_PATH}#away-address`,
  playability: `${HOUSEHOLD_PLAYBACK_PATH}#playability`,
  "playability-report": `${HOUSEHOLD_PLAYBACK_PATH}#playability`,
  copies: `${HOUSEHOLD_PLAYBACK_PATH}#copies`,
  "copies-ahead": `${HOUSEHOLD_PLAYBACK_PATH}#copies`,
  "copies-folder": `${HOUSEHOLD_PLAYBACK_PATH}#copies`,
  "copies-budget": `${HOUSEHOLD_PLAYBACK_PATH}#copies`,
};

function pathOnly(pathname: string) {
  const raw = String(pathname || "").split("?")[0].split("#")[0].trim();
  if (!raw || raw === "/") return "/";
  return raw.replace(/\/+$/, "") || "/";
}

function hashId(hash: string) {
  const raw = String(hash || "").replace(/^#/, "").split("?")[0].split("&")[0].trim().toLowerCase();
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/**
 * Where an old Profile playback anchor should land.
 * Returns null when the address is a personal Profile destination (badges, pause, text size).
 */
export function householdPlaybackRedirect(pathname: string, hash = ""): string | null {
  const path = pathOnly(pathname);
  if (PROFILE_ROUTES.has(path)) return HOUSEHOLD_PLAYBACK_PATH;
  if (!PROFILE_PATHS.has(path)) return null;
  const id = hashId(hash);
  if (!id || id.length > 80) return null;
  return PROFILE_HASHES[id] || null;
}
