import { useEffect, useState } from "react";
import {
  loadVoicePrefs,
  saveVoicePrefs,
  speechSupported,
} from "../../lib/voicePrefs.js";

export default function VoicePage() {
  const [prefs, setPrefs] = useState(loadVoicePrefs);
  const support = speechSupported();

  useEffect(() => {
    saveVoicePrefs(prefs);
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
          Preferences stay on this device until account sync ships.
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
        <p className="status status-secondary" data-testid="voice-input-unsupported">
          Speech recognition is not available in this browser. Chromium-based browsers work best.
        </p>
      ) : (
        <p className="field-help">
          When enabled, a mic appears next to the chat send button. Dictation fills the composer — Enter
          still sends.
        </p>
      )}

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
        <p className="status status-secondary" data-testid="voice-speak-unsupported">
          Speech synthesis is not available in this browser.
        </p>
      ) : (
        <p className="field-help">
          Assistant text replies are read aloud. You can mute mid-reply from the composer.
        </p>
      )}

      <p className="field-help">
        Audio may be processed by your browser or OS speech service. CuratorX stores transcripts as chat
        text, not raw audio.
      </p>
    </section>
  );
}
