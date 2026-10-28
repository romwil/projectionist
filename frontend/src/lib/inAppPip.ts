import type {JsonObject, JsParam} from "../api/types";
/** In-app Play shrink — keep one library player mounted across routes. */

export const SHRINK_ONTO_PAGE_LABEL = "Shrink onto the page";
export const POP_OUT_OF_WINDOW_LABEL = "Pop out of the window";

/**
 * Survives a document reload (manual refresh, or iPad Safari reload after unlock).
 * Rating key + playhead only. Never a stream URL or Plex token.
 */
export const SHRUNK_PLAY_STORAGE_KEY = "projectionist.shrunkPlay";

const SHRUNK_TITLE_MAX = 180;

function pathOnly(pathname: JsParam) {
  return String(pathname || "").split("#")[0].split("?")[0];
}

export function watchRatingKeyFromPath(pathname: JsParam) {
  const path = pathOnly(pathname);
  const match = path.match(/^\/watch\/([^/]+)\/?$/);
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return "";
  }
}

export function isLibraryPopoutPath(pathname: JsParam) {
  return /^\/watch\/[^/]+\/popout\/?$/.test(pathOnly(pathname));
}

/** Page to land on when shrinking. Never a watch URL or an off-site path. */
export function normalizeReturnTo(returnTo: JsParam) {
  const raw = String(returnTo || "").trim();
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || raw.includes("..")) {
    return "/chat";
  }
  const pathname = pathOnly(raw);
  if (pathname === "/watch" || pathname.startsWith("/watch/")) return "/chat";
  return raw;
}

function playheadMs(video: JsParam) {
  const seconds = Number(video?.currentTime);
  if (!Number.isFinite(seconds)) return 0;
  return Math.max(0, Math.round(seconds * 1000));
}

/**
 * Shrink keeps the current playhead. It must not call pause.
 * @returns {{ presentation: "pip", ratingKey: string, returnTo: string, paused: boolean, offsetMs: number, title: string }}
 */
export function shrinkOntoPage(video: JsParam, { ratingKey = "", returnTo = "", title = "" }: JsParam = {}) {
  const key = String(ratingKey || "").trim();
  return {
    presentation: "pip",
    ratingKey: key,
    returnTo: normalizeReturnTo(returnTo),
    paused: Boolean(video?.paused),
    offsetMs: playheadMs(video),
    title: String(title || "").slice(0, SHRUNK_TITLE_MAX),
  };
}

/** Whitelist persisted fields. Drops stream URLs, tokens, and anything else. */
export function shrunkPlayRecord({ ratingKey = "", offsetMs = 0, title = "" }: JsParam = {}) {
  const key = String(ratingKey || "").trim();
  if (!key) return null;
  const offset = Math.floor(Number(offsetMs) || 0);
  return {
    shrunk: true,
    ratingKey: key,
    offsetMs: offset > 0 ? offset : 0,
    title: String(title || "").slice(0, SHRUNK_TITLE_MAX),
  };
}

export function persistShrunkPlay(record: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const safe = shrunkPlayRecord(record);
  if (!safe || !storage?.setItem) return null;
  try {
    storage.setItem(SHRUNK_PLAY_STORAGE_KEY, JSON.stringify(safe));
  } catch {
    return null;
  }
  return safe;
}

export function readShrunkPlay(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  if (!storage?.getItem) return null;
  try {
    const raw = storage.getItem(SHRUNK_PLAY_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.shrunk !== true) return null;
    return shrunkPlayRecord(parsed);
  } catch {
    return null;
  }
}

export function clearShrunkPlay(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    storage?.removeItem?.(SHRUNK_PLAY_STORAGE_KEY);
  } catch {
    // storage unavailable
  }
}

/**
 * Fresh document state. The overlay returns only when a shrunk flag was stored.
 * A full watch page or the browser pop-out does not resurrect it.
 */
export function initialPipState(pathname = "", storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  if (isLibraryPopoutPath(pathname)) return null;
  if (watchRatingKeyFromPath(pathname)) {
    clearShrunkPlay(storage);
    return null;
  }
  const stored = readShrunkPlay(storage);
  if (!stored) return null;
  return {
    ratingKey: stored.ratingKey,
    returnTo: "/chat",
    offsetMs: stored.offsetMs,
    title: stored.title,
    restored: true,
  };
}

/**
 * iPad Safari often rejects unmuted autoplay after a reload.
 * Try sound first. If that is blocked, start the picture muted and let the
 * next tap of the small player unmute. Never reloads the document.
 */
export async function playShrunkAfterReload(video: JsParam) {
  if (!video?.play) return { playing: false, muted: false, unmuteOnTap: false };
  try {
    video.muted = false;
    delete video.dataset?.shrunkHoldMute;
    await video.play();
    return { playing: true, muted: false, unmuteOnTap: false };
  } catch {
    try {
      video.muted = true;
      if (video.dataset) video.dataset.shrunkHoldMute = "1";
      await video.play();
      return { playing: true, muted: true, unmuteOnTap: true };
    } catch {
      return { playing: false, muted: Boolean(video.muted), unmuteOnTap: true };
    }
  }
}

/**
 * Whether the lifted player element stays mounted.
 * A pip session survives client navigations to chat, Explore, and search.
 * The pop-out window owns a separate player and does not use this host.
 */
export function resolvePlaybackHost({ pathname, session }: JsParam = {}) {
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
export function playbackMountKey(host: JsParam) {
  if (!host?.active || !host.ratingKey) return "";
  return `library-play:${host.ratingKey}`;
}

/** Shrink sits on the player bar. Pop-out stays a separate window action. */
export function playerBarActions({ presentation = "stage", popoutWindow = false, phone = false }: JsParam = {}) {
  return {
    shrinkOntoPage: presentation !== "pip" && !popoutWindow,
    popOutOfWindow: !phone && !popoutWindow,
  };
}
