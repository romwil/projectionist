import type {JsonObject, LibraryItem, JsParam} from "../api/types";
const FONT_SIZES: Record<string, any> = {
  small: "13px",
  medium: "15px",
  large: "17px",
};

export const UI_THEME_STORAGE_KEY = "projectionist.ui_theme";
/** Opt-in: soft-pause /watch when the tab or Space is backgrounded. Default off = keep playing. */
export const PAUSE_WHEN_BACKGROUNDED_KEY = "projectionist.pause_when_backgrounded";
/** Opt-in: black letterbox instead of blurred poster art around the Play frame. Default art. */
export const PLAY_BLACK_FRAME_KEY = "projectionist.play_black_frame";
export const UI_PREFS_CHANGED_EVENT = "projectionist:ui-prefs";

const THEME_PREFS = new Set(["lights_up", "lights_down", "system"]);

/** Apply the user's preferred base font size via CSS variable on :root. */
export function applyUiFontSize(size: JsParam) {
  const key = FONT_SIZES[size] ? size : "medium";
  const px = FONT_SIZES[key];
  if (typeof document === "undefined") return key;
  document.documentElement.style.setProperty("--base-font-size", px);
  document.documentElement.dataset.fontSize = key;
  return key;
}

export function normalizeUiFontSize(size: JsParam) {
  return FONT_SIZES[size] ? size : "medium";
}

export function normalizeUiTheme(theme: JsParam) {
  const cleaned = String(theme ?? "system")
    .trim()
    .toLowerCase();
  return THEME_PREFS.has(cleaned) ? cleaned : "system";
}

/**
 * Resolve preference → effective theme (`lights_up` | `lights_down`).
 * @param {string} pref
 * @param {{ matches?: boolean } | ((query: string) => { matches: boolean }) | null} [media]
 */
export function resolveEffectiveTheme(pref: JsParam, media: JsParam) {
  const normalized = normalizeUiTheme(pref);
  if (normalized !== "system") return normalized;

  let prefersLight = false;
  try {
    if (media && typeof media === "object" && "matches" in media) {
      prefersLight = Boolean(media.matches);
    } else if (typeof media === "function") {
      prefersLight = Boolean(media("(prefers-color-scheme: light)")?.matches);
    } else if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      prefersLight = Boolean(window.matchMedia("(prefers-color-scheme: light)").matches);
    }
  } catch {
    prefersLight = false;
  }
  return prefersLight ? "lights_up" : "lights_down";
}

/** Map effective theme (`lights_up` | `lights_down`) to `html[data-theme]`. */
export function themeToDataAttr(effective: JsParam) {
  return effective === "lights_up" ? "lights-up" : "lights-down";
}

export function loadStoredUiTheme(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    const current = storage?.getItem?.(UI_THEME_STORAGE_KEY);
    if (current != null && String(current).trim() !== "") {
      return normalizeUiTheme(current);
    }
    return "system";
  } catch {
    return "system";
  }
}

export function persistUiTheme(theme: JsParam, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const normalized = normalizeUiTheme(theme);
  try {
    storage?.setItem?.(UI_THEME_STORAGE_KEY, normalized);
  } catch {
    // localStorage unavailable
  }
  return normalized;
}

/**
 * Apply theme preference to the document and optionally persist to localStorage.
 * @returns {{ preference: string, effective: string }}
 */
export function applyUiTheme(theme: JsParam, { persist = true, media, storage }: JsParam = {}) {
  const preference = normalizeUiTheme(theme);
  const effective = resolveEffectiveTheme(preference, media);
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = themeToDataAttr(effective);
    document.documentElement.style.colorScheme = effective === "lights_up" ? "light" : "dark";
  }
  if (persist) {
    persistUiTheme(preference, storage);
  }
  return { preference, effective };
}

/** Cycle Lights Up → Lights Down → Match system. */
export function cycleUiTheme(current: JsParam) {
  const order = ["lights_up", "lights_down", "system"];
  const idx = order.indexOf(normalizeUiTheme(current));
  return order[(idx + 1) % order.length];
}

export function themePreferenceLabel(pref: JsParam) {
  switch (normalizeUiTheme(pref)) {
    case "lights_up":
      return "Lights Up";
    case "lights_down":
      return "Lights Down";
    default:
      return "Match system";
  }
}

export function themeControlIcon(pref: JsParam, media?: JsParam) {
  const preference = normalizeUiTheme(pref);
  if (preference === "system") return "brightness_auto";
  return resolveEffectiveTheme(preference, media) === "lights_up" ? "light_mode" : "dark_mode";
}

function notifyUiPrefsChanged(detail: LibraryItem | null | undefined = {}) {
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(UI_PREFS_CHANGED_EVENT, { detail }));
    }
  } catch {
    // Non-DOM / test environments
  }
}

/**
 * Device-local playback pref. Default false: Mac Spaces / tab hide keep /watch playing.
 * Opt-in true: soft-pause when backgrounded (HDMI kiosk / battery savers).
 */
export function loadPauseWhenBackgrounded(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    return storage?.getItem?.(PAUSE_WHEN_BACKGROUNDED_KEY) === "true";
  } catch {
    return false;
  }
}

export function persistPauseWhenBackgrounded(enabled: boolean, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const value = Boolean(enabled);
  try {
    storage?.setItem?.(PAUSE_WHEN_BACKGROUNDED_KEY, value ? "true" : "false");
  } catch {
    // localStorage unavailable
  }
  notifyUiPrefsChanged({ pauseWhenBackgrounded: value });
  return value;
}

/** Device-local Play stage: false = blurred poster border (default), true = black frame. */
export function loadPlayBlackFrame(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  try {
    return storage?.getItem?.(PLAY_BLACK_FRAME_KEY) === "true";
  } catch {
    return false;
  }
}

export function persistPlayBlackFrame(enabled: boolean, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null | undefined = globalThis.localStorage) {
  const value = Boolean(enabled);
  try {
    storage?.setItem?.(PLAY_BLACK_FRAME_KEY, value ? "true" : "false");
  } catch {
    // localStorage unavailable
  }
  notifyUiPrefsChanged({ playBlackFrame: value });
  return value;
}

export function playFrameMenuLabel(blackFrame: JsParam) {
  return blackFrame ? "Use poster border" : "Black frame";
}
