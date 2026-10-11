/** In-app Play shrink — keep one library player mounted across routes. */

export const SHRINK_ONTO_PAGE_LABEL = "Shrink onto the page";
export const POP_OUT_OF_WINDOW_LABEL = "Pop out of the window";

function pathOnly(pathname) {
  return String(pathname || "").split("#")[0].split("?")[0];
}

export function watchRatingKeyFromPath(pathname) {
  const path = pathOnly(pathname);
  const match = path.match(/^\/watch\/([^/]+)\/?$/);
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return "";
  }
}

export function isLibraryPopoutPath(pathname) {
  return /^\/watch\/[^/]+\/popout\/?$/.test(pathOnly(pathname));
}

/** Page to land on when shrinking. Never a watch URL or an off-site path. */
export function normalizeReturnTo(returnTo) {
  const raw = String(returnTo || "").trim();
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || raw.includes("..")) {
    return "/chat";
  }
  const pathname = pathOnly(raw);
  if (pathname === "/watch" || pathname.startsWith("/watch/")) return "/chat";
  return raw;
}

/**
 * Shrink keeps the current playhead. It must not call pause.
 * @returns {{ presentation: "pip", ratingKey: string, returnTo: string, paused: boolean }}
 */
export function shrinkOntoPage(video, { ratingKey = "", returnTo = "" } = {}) {
  const key = String(ratingKey || "").trim();
  return {
    presentation: "pip",
    ratingKey: key,
    returnTo: normalizeReturnTo(returnTo),
    paused: Boolean(video?.paused),
  };
}

/**
 * Whether the lifted player element stays mounted.
 * A pip session survives client navigations to chat, Explore, and search.
 * The pop-out window owns a separate player and does not use this host.
 */
export function resolvePlaybackHost({ pathname, session } = {}) {
  if (isLibraryPopoutPath(pathname)) {
    return { active: false, presentation: "idle", ratingKey: "" };
  }
  const routeKey = watchRatingKeyFromPath(pathname);
  const pipKey = session?.presentation === "pip" ? String(session.ratingKey || "").trim() : "";
  if (pipKey && !routeKey) {
    return { active: true, presentation: "pip", ratingKey: pipKey };
  }
  if (routeKey) {
    return { active: true, presentation: "stage", ratingKey: routeKey };
  }
  return { active: false, presentation: "idle", ratingKey: "" };
}

/** Stable React key so stage → pip → other routes reuse the same player element. */
export function playbackMountKey(host) {
  if (!host?.active || !host.ratingKey) return "";
  return `library-play:${host.ratingKey}`;
}

/** Shrink sits on the player bar. Pop-out stays a separate window action. */
export function playerBarActions({ presentation = "stage", popoutWindow = false, phone = false } = {}) {
  return {
    shrinkOntoPage: presentation !== "pip" && !popoutWindow,
    popOutOfWindow: !phone && !popoutWindow,
  };
}
