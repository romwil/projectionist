const FONT_SIZES = {
  small: "13px",
  medium: "15px",
  large: "17px",
};

export const UI_THEME_STORAGE_KEY = "curatorx.ui_theme";

const THEME_PREFS = new Set(["lights_up", "lights_down", "system"]);

/** Apply the user's preferred base font size via CSS variable on :root. */
export function applyUiFontSize(size) {
  const key = FONT_SIZES[size] ? size : "medium";
  const px = FONT_SIZES[key];
  if (typeof document === "undefined") return key;
  document.documentElement.style.setProperty("--base-font-size", px);
  document.documentElement.dataset.fontSize = key;
  return key;
}

export function normalizeUiFontSize(size) {
  return FONT_SIZES[size] ? size : "medium";
}

export function normalizeUiTheme(theme) {
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
export function resolveEffectiveTheme(pref, media) {
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
export function themeToDataAttr(effective) {
  return effective === "lights_up" ? "lights-up" : "lights-down";
}

export function loadStoredUiTheme(storage = globalThis.localStorage) {
  try {
    return normalizeUiTheme(storage?.getItem?.(UI_THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

export function persistUiTheme(theme, storage = globalThis.localStorage) {
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
export function applyUiTheme(theme, { persist = true, media, storage } = {}) {
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
export function cycleUiTheme(current) {
  const order = ["lights_up", "lights_down", "system"];
  const idx = order.indexOf(normalizeUiTheme(current));
  return order[(idx + 1) % order.length];
}

export function themePreferenceLabel(pref) {
  switch (normalizeUiTheme(pref)) {
    case "lights_up":
      return "Lights Up";
    case "lights_down":
      return "Lights Down";
    default:
      return "Match system";
  }
}

export function themeControlIcon(pref, media) {
  const preference = normalizeUiTheme(pref);
  if (preference === "system") return "brightness_auto";
  return resolveEffectiveTheme(preference, media) === "lights_up" ? "light_mode" : "dark_mode";
}
