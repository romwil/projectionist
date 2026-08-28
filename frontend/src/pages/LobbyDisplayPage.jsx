import { useEffect, useMemo, useState } from "react";
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

const FEED_EXAMPLES = [
  { id: "recently_added", label: "Recently added" },
  { id: "recently_released", label: "Recently released" },
  { id: "trending", label: "Trending" },
];

function lobbyKioskUrl(host, port, feed) {
  const base = `http://${host}:${port}/`;
  if (!feed || feed === "recently_added") return base;
  return `${base}?feed=${encodeURIComponent(feed)}`;
}

export default function LobbyDisplayPage() {
  const [theater, setTheater] = useState(EMPTY);
  const [saveStatus, setSaveStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);
  const [copyStatus, setCopyStatus] = useState(null);
  const [lanHost, setLanHost] = useState("<nas-ip>");

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hostname) {
      setLanHost(window.location.hostname);
    }
  }, []);

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
      const saved = await saveSettings(payload);
      setTheater((prev) => ({ ...prev, ...(saved.theater || {}) }));
      setSaveStatus({ type: "success", message: "Lobby display settings saved." });
    } catch (error) {
      setSaveStatus({ type: "error", message: error.message || "Save failed." });
    } finally {
      setSaving(false);
    }
  }

  async function copyUrl(feed) {
    const port = Number(theater.host_port) || 8791;
    const url = lobbyKioskUrl(lanHost, port, feed);
    try {
      await navigator.clipboard.writeText(url);
      setCopyStatus(`Copied ${feed ? `?feed=${feed}` : "kiosk URL"}`);
      window.setTimeout(() => setCopyStatus(null), 2400);
    } catch {
      setCopyStatus("Could not copy — select the URL manually.");
    }
  }

  const port = Number(theater.host_port) || 8791;
  const kioskUrl = useMemo(() => lobbyKioskUrl(lanHost, port), [lanHost, port]);
  const previewUrl = theater.enabled ? kioskUrl : null;

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

      <aside className="editorial-section lobby-setup-guide" data-testid="lobby-setup-guide">
        <header className="editorial-header">
          <p className="eyebrow">Setup guide</p>
          <h2 className="editorial-lede">Point a wall browser at the theater port</h2>
          <p className="editorial-meta">
            The lobby runs as a separate LAN service on port{" "}
            <code>{port}</code> (env <code>PROJECTIONIST_THEATER_PORT</code>, default 8791). It does not
            share the main admin UI port.
          </p>
        </header>

        <div className="lobby-setup-url-row">
          <code className="lobby-setup-url" data-testid="lobby-kiosk-url">
            {kioskUrl}
          </code>
          <div className="lobby-setup-actions">
            <a
              href={kioskUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="ghost"
              data-testid="lobby-open-kiosk"
            >
              Open kiosk
            </a>
            <button type="button" className="ghost" data-testid="lobby-copy-url" onClick={() => copyUrl()}>
              Copy URL
            </button>
          </div>
        </div>
        {copyStatus ? <p className="wizard-note">{copyStatus}</p> : null}

        <section className="lobby-setup-block">
          <h3>Feed URL examples</h3>
          <p>
            Append <code>?feed=</code> to rotate a different idle deck when nothing is playing on Plex.
          </p>
          <ul className="editorial-links">
            {FEED_EXAMPLES.map((feed) => {
              const url = lobbyKioskUrl(lanHost, port, feed.id);
              return (
                <li key={feed.id}>
                  <span>
                    <strong>{feed.label}</strong> — <code>{url}</code>
                  </span>
                  <button
                    type="button"
                    className="ghost lobby-feed-copy"
                    data-testid={`lobby-copy-feed-${feed.id}`}
                    onClick={() => copyUrl(feed.id)}
                  >
                    Copy
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="lobby-setup-block">
          <h3>Header plate modes</h3>
          <p>
            <strong>Dynamic</strong> — NOW PLAYING and feed labels appear on the marquee header when idle.
          </p>
          <p>
            <strong>Static</strong> — your fixed label stays on the header; feed titles move to the poster
            footer caption instead.
          </p>
        </section>

        {previewUrl ? (
          <section className="lobby-setup-block">
            <h3>Live preview</h3>
            <p className="editorial-meta">Scaled iframe — same URL your wall screen will load.</p>
            <iframe
              title="Lobby kiosk preview"
              className="lobby-setup-preview"
              src={previewUrl}
              data-testid="lobby-preview-iframe"
            />
          </section>
        ) : (
          <p className="wizard-note">Enable the lobby below to show a live preview iframe.</p>
        )}
      </aside>

      <form onSubmit={handleSave}>
        <SettingsPanel title="Lobby theater" testId="lobby-theater-panel">
          <SettingsToggle
            checked={Boolean(theater.enabled)}
            onChange={(enabled) => patch({ enabled })}
            label="Enable lobby display"
            testId="lobby-enabled-toggle"
          />
          <p className="wizard-note">
            When on, open <code>{kioskUrl}</code> from a LAN browser. Do not reverse-proxy this port to the
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
              <option value="dynamic">Dynamic (NOW PLAYING / feed labels on header)</option>
              <option value="static">Static label (feed labels on poster footer)</option>
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
