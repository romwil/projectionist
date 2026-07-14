import { useEffect, useState } from "react";

const STORAGE_KEY = "curatorx.voicePrefs";

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { voice_input_enabled: false, voice_speak_replies: false };
    return { voice_input_enabled: false, voice_speak_replies: false, ...JSON.parse(raw) };
  } catch {
    return { voice_input_enabled: false, voice_speak_replies: false };
  }
}

function speechSupported() {
  if (typeof window === "undefined") return { input: false, speak: false };
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  return {
    input: Boolean(Recognition),
    speak: typeof window.speechSynthesis !== "undefined",
  };
}

export default function VoicePage() {
  const [prefs, setPrefs] = useState(loadPrefs);
  const support = speechSupported();

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // localStorage unavailable
    }
  }, [prefs]);

  function toggle(key) {
    setPrefs((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <section className="settings-section" data-testid="settings-voice">
      <header className="settings-section-header">
        <h2>Voice</h2>
        <p>
          Talk to your curator with the browser mic, and optionally hear replies spoken aloud.
          Full composer controls arrive in a follow-on release.
        </p>
      </header>

      <label className="config-toggle" data-testid="voice-input-toggle">
        <input
          type="checkbox"
          checked={Boolean(prefs.voice_input_enabled)}
          disabled={!support.input}
          onChange={() => toggle("voice_input_enabled")}
        />
        <span>Enable voice input</span>
      </label>
      {!support.input ? (
        <p className="status status-secondary">
          Speech recognition is not available in this browser. Chromium-based browsers work best.
        </p>
      ) : null}

      <label className="config-toggle" data-testid="voice-speak-toggle">
        <input
          type="checkbox"
          checked={Boolean(prefs.voice_speak_replies)}
          disabled={!support.speak}
          onChange={() => toggle("voice_speak_replies")}
        />
        <span>Speak replies</span>
      </label>
      {!support.speak ? (
        <p className="status status-secondary">Speech synthesis is not available in this browser.</p>
      ) : null}

      <p className="field-help">
        Audio may be processed by your browser or OS speech service. CuratorX stores transcripts as chat
        text, not raw audio. Prefs are saved locally until account sync ships.
      </p>
    </section>
  );
}
