export const VOICE_PREFS_KEY = "curatorx.voicePrefs";
export const VOICE_PREFS_EVENT = "curatorx:voicePrefs";

export const DEFAULT_VOICE_PREFS = Object.freeze({
  voice_input_enabled: false,
  voice_speak_replies: false,
});

export function normalizeVoicePrefs(raw = {}) {
  return {
    voice_input_enabled: Boolean(raw.voice_input_enabled),
    voice_speak_replies: Boolean(raw.voice_speak_replies),
  };
}

export function loadVoicePrefs(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem?.(VOICE_PREFS_KEY);
    if (!raw) return { ...DEFAULT_VOICE_PREFS };
    return normalizeVoicePrefs({ ...DEFAULT_VOICE_PREFS, ...JSON.parse(raw) });
  } catch {
    return { ...DEFAULT_VOICE_PREFS };
  }
}

export function saveVoicePrefs(prefs, storage = globalThis.localStorage) {
  const next = normalizeVoicePrefs(prefs);
  try {
    storage?.setItem?.(VOICE_PREFS_KEY, JSON.stringify(next));
  } catch {
    // localStorage unavailable
  }
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(VOICE_PREFS_EVENT, { detail: next }));
    }
  } catch {
    // CustomEvent unavailable
  }
  return next;
}

export function speechSupported(win = typeof window !== "undefined" ? window : undefined) {
  if (!win) return { input: false, speak: false };
  const Recognition = win.SpeechRecognition || win.webkitSpeechRecognition;
  return {
    input: Boolean(Recognition),
    speak: typeof win.speechSynthesis !== "undefined",
  };
}

export function getSpeechRecognitionCtor(win = typeof window !== "undefined" ? window : undefined) {
  if (!win) return null;
  return win.SpeechRecognition || win.webkitSpeechRecognition || null;
}
