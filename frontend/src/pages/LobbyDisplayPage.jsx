import { useEffect, useState } from "react";
import { getSettings, saveSettings } from "../api/client";
import InlineAlert from "../components/InlineAlert";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";
import SettingsToggle from "../components/settings/SettingsToggle";

const EMPTY = {
  enabled: false,
  orientation: "landscape",
  audience: "everyone",
  idle_mode: "empty",
  multi_mode: "rotator",
  header_mode: "dynamic",
  static_label: "",
  rotate_seconds: 12,
  host_port: 8791,
};

export default function LobbyDisplayPage() {
  const [theater, setTheater] = useState(EMPTY);
  const [saveStatus, setSaveStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    getSettings()
      .then((data) => {
        setTheater((prev) => ({ ...prev, ...(data.theater || {}) }));
        setReady(true);
      })
      .catch((error) => {
        setSaveStatus({ type: "error", message: error.message || "Could not load settings." });
        setReady(true);
      });
  }, []);

  function patch(next) {
    setTheater((prev) => ({ ...prev, ...next }));
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setSaveStatus(null);
    try {
      const current = await getSettings();
      const payload = {
        ...current,
        theater: {
          enabled: Boolean(theater.enabled),
          orientation: theater.orientation === "portrait" ? "portrait" : "landscape",
          audience: theater.audience === "household" ? "household" : "everyone",
          idle_mode: theater.idle_mode === "now_available" ? "now_available" : "empty",
          multi_mode: theater.multi_mode === "panelled" ? "panelled" : "rotator",
          header_mode: theater.header_mode === "static" ? "static" : "dynamic",
          static_label: String(theater.static_label || "").slice(0, 24),
          rotate_seconds: Math.max(8, Math.min(60, Number(theater.rotate_seconds) || 12)),
        },
      };
      // Drop masked secret placeholders / derived fields the API rejects or ignores.
      const saved = await saveSettings(payload);
      setTheater((prev) => ({ ...prev, ...(saved.theater || {}) }));
      setSaveStatus({ type: "success", message: "Lobby display settings saved." });
    } catch (error) {
      setSaveStatus({ type: "error", message: error.message || "Save failed." });
    } finally {
      setSaving(false);
    }
  }

  const port = Number(theater.host_port) || 8791;
  const openUrl = `http://<nas-ip>:${port}/`;

  return (
    <div className="settings-page" data-testid="lobby-display-page">
      <SettingsPageHeader
        title="Lobby display"
        lead="Open a cinema lightbox on your LAN for wall screens, Apple TV, or a Pi browser. Unauthenticated on a dedicated port — keep it off the public internet."
      />

      {!ready ? <p className="wizard-note">Loading…</p> : null}

      {saveStatus ? (
        <InlineAlert type={saveStatus.type} message={saveStatus.message} onDismiss={() => setSaveStatus(null)} />
      ) : null}

      <form onSubmit={handleSave}>
        <SettingsPanel title="Lobby theater" testId="lobby-theater-panel">
          <SettingsToggle
            checked={Boolean(theater.enabled)}
            onChange={(enabled) => patch({ enabled })}
            label="Enable lobby display"
            testId="lobby-enabled-toggle"
          />
          <p className="wizard-note">
            When on, open <code>{openUrl}</code> from a LAN browser. Port comes from{" "}
            <code>PROJECTIONIST_THEATER_PORT</code> (default {port}). Do not reverse-proxy this port to the
            public internet.
          </p>

          <label className="config-field">
            <span>Orientation</span>
            <select
              value={theater.orientation || "landscape"}
              onChange={(e) => patch({ orientation: e.target.value })}
              data-testid="lobby-orientation"
            >
              <option value="landscape">Landscape</option>
              <option value="portrait">Portrait</option>
            </select>
          </label>

          <label className="config-field">
            <span>Audience</span>
            <select
              value={theater.audience || "everyone"}
              onChange={(e) => patch({ audience: e.target.value })}
              data-testid="lobby-audience"
            >
              <option value="everyone">Everyone on the Plex server</option>
              <option value="household">Household members only</option>
            </select>
          </label>

          <label className="config-field">
            <span>When idle</span>
            <select
              value={theater.idle_mode || "empty"}
              onChange={(e) => patch({ idle_mode: e.target.value })}
              data-testid="lobby-idle-mode"
            >
              <option value="empty">Empty well</option>
              <option value="now_available">Rotate recently added movies</option>
            </select>
          </label>

          <label className="config-field">
            <span>Multiple sessions</span>
            <select
              value={theater.multi_mode || "rotator"}
              onChange={(e) => patch({ multi_mode: e.target.value })}
              data-testid="lobby-multi-mode"
            >
              <option value="rotator">One lightbox, rotate</option>
              <option value="panelled">Hallway row of lightboxes</option>
            </select>
          </label>

          <label className="config-field">
            <span>Header plate</span>
            <select
              value={theater.header_mode || "dynamic"}
              onChange={(e) => patch({ header_mode: e.target.value })}
              data-testid="lobby-header-mode"
            >
              <option value="dynamic">Dynamic (NOW PLAYING / NOW AVAILABLE)</option>
              <option value="static">Static label</option>
            </select>
          </label>

          {theater.header_mode === "static" ? (
            <label className="config-field">
              <span>Static label</span>
              <input
                type="text"
                maxLength={24}
                value={theater.static_label || ""}
                onChange={(e) => patch({ static_label: e.target.value })}
                placeholder="NOW PLAYING"
                data-testid="lobby-static-label"
              />
            </label>
          ) : null}

          <label className="config-field">
            <span>Rotate every (seconds)</span>
            <input
              type="number"
              min={8}
              max={60}
              value={theater.rotate_seconds || 12}
              onChange={(e) => patch({ rotate_seconds: Number(e.target.value) || 12 })}
              data-testid="lobby-rotate-seconds"
            />
          </label>

          <div className="settings-actions">
            <button type="submit" className="primary" disabled={saving} data-testid="lobby-save">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </SettingsPanel>
      </form>
    </div>
  );
}
