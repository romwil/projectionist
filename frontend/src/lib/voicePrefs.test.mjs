import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_VOICE_PREFS,
  loadVoicePrefs,
  normalizeVoicePrefs,
  saveVoicePrefs,
  speechSupported,
  VOICE_PREFS_KEY,
} from "./voicePrefs.js";

function memoryStorage(seed = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      map.set(key, String(value));
    },
    removeItem(key) {
      map.delete(key);
    },
  };
}

test("normalizeVoicePrefs coerces booleans", () => {
  assert.deepEqual(normalizeVoicePrefs({ voice_input_enabled: 1, voice_speak_replies: "yes" }), {
    voice_input_enabled: true,
    voice_speak_replies: true,
  });
  assert.deepEqual(normalizeVoicePrefs({}), { ...DEFAULT_VOICE_PREFS });
});

test("loadVoicePrefs returns defaults when empty or corrupt", () => {
  assert.deepEqual(loadVoicePrefs(memoryStorage()), { ...DEFAULT_VOICE_PREFS });
  assert.deepEqual(
    loadVoicePrefs(memoryStorage({ [VOICE_PREFS_KEY]: "{not-json" })),
    { ...DEFAULT_VOICE_PREFS }
  );
});

test("loadVoicePrefs and saveVoicePrefs round-trip", () => {
  const storage = memoryStorage();
  const saved = saveVoicePrefs(
    { voice_input_enabled: true, voice_speak_replies: false },
    storage
  );
  assert.deepEqual(saved, { voice_input_enabled: true, voice_speak_replies: false });
  assert.deepEqual(loadVoicePrefs(storage), saved);
});

test("speechSupported inspects Recognition and speechSynthesis", () => {
  assert.deepEqual(speechSupported(undefined), { input: false, speak: false });
  assert.deepEqual(
    speechSupported({ speechSynthesis: {} }),
    { input: false, speak: true }
  );
  assert.deepEqual(
    speechSupported({ webkitSpeechRecognition: function Recognition() {}, speechSynthesis: {} }),
    { input: true, speak: true }
  );
});
