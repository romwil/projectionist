import { useEffect, useState } from "react";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import SettingsToggle from "../../components/settings/SettingsToggle";
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

  function setPref(key, value) {
    setPrefs((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="settings-stack" data-testid="settings-voice">
      <SettingsPageHeader title="Voice" testId="settings-voice-header">
        Talk to your curator with the browser mic, and optionally hear replies spoken aloud. Preferences
        stay on this device until account sync ships.
      </SettingsPageHeader>

      <SettingsPanel title="Input &amp; output" testId="settings-voice-panel">
        <SettingsToggle
          testId="voice-input-toggle"
          id="voice-input-enabled"
          checked={prefs.voice_input_enabled}
          disabled={!support.input}
          label="Enable voice input"
          help={
            support.input
              ? "When enabled, a mic appears next to the chat send button. Dictation fills the composer — Enter still sends."
              : "Speech recognition is not available in this browser. Chromium-based browsers work best."
          }
          onChange={(value) => setPref("voice_input_enabled", value)}
        />

        <SettingsToggle
          testId="voice-speak-toggle"
          id="voice-speak-replies"
          checked={prefs.voice_speak_replies}
          disabled={!support.speak}
          label="Speak replies"
          help={
            support.speak
              ? "Assistant text replies are read aloud. You can mute mid-reply from the composer."
              : "Speech synthesis is not available in this browser."
          }
          onChange={(value) => setPref("voice_speak_replies", value)}
        />
      </SettingsPanel>

      <SettingsPanel testId="settings-voice-privacy">
        <p className="field-help settings-voice-privacy">
          Audio may be processed by your browser or OS speech service. CuratorX stores transcripts as chat
          text, not raw audio.
        </p>
      </SettingsPanel>
    </div>
  );
}
