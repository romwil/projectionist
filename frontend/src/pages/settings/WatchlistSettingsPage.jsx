import { useCallback, useEffect, useState } from "react";
import {
  formatApiError,
  getWatchlistSync,
  relativeTime,
  runWatchlistSync,
  updateWatchlistSync,
} from "../../api/client";

export default function WatchlistSettingsPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getWatchlistSync();
      setStatus(next);
      setMessage(null);
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function patchSettings(patch) {
    setSaving(true);
    setMessage(null);
    try {
      const next = await updateWatchlistSync(patch);
      setStatus(next);
      setMessage({ type: "success", text: "Watchlist sync settings saved." });
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleSyncNow() {
    setSyncing(true);
    setMessage(null);
    try {
      const result = await runWatchlistSync({ direction: "both" });
      setStatus(result);
      if (result.ok === false && result.reason === "missing_token") {
        setMessage({
          type: "error",
          text: result.message || "Re-sign in with Plex to sync your Discover watchlist.",
        });
      } else {
        setMessage({
          type: "success",
          text: `Synced — pulled ${result.pulled ?? 0}, pushed ${result.pushed ?? 0}.`,
        });
      }
    } catch (error) {
      setMessage({ type: "error", text: formatApiError(error) });
    } finally {
      setSyncing(false);
    }
  }

  if (loading && !status) {
    return (
      <section className="settings-section" data-testid="settings-watchlist">
        <h2>Watchlist</h2>
        <p className="status status-secondary">Loading sync status…</p>
      </section>
    );
  }

  return (
    <section className="settings-section" data-testid="settings-watchlist">
      <header className="settings-section-header">
        <h2>Watchlist</h2>
        <p>
          Pins live in chat. When sync is on, CuratorX pulls your Plex Discover watchlist and pushes
          local pins using your personal Sign-in-with-Plex token.
        </p>
      </header>

      <div className="settings-subsection" data-testid="watchlist-sync-panel">
        <h3>Plex Discover sync</h3>
        <p className="status status-secondary" data-testid="watchlist-sync-token-status">
          {status?.has_account_token
            ? "Account token on file from Sign in with Plex."
            : status?.has_plex_token
              ? status.message || "Using server Plex token (prefer Sign in with Plex)."
              : status?.message || "Re-sign in with Plex to sync your Discover watchlist."}
        </p>
        <p className="status status-secondary" data-testid="watchlist-last-synced">
          Last synced:{" "}
          {status?.last_synced_at ? relativeTime(status.last_synced_at) : "never"}
        </p>

        <label className="settings-toggle-row">
          <input
            type="checkbox"
            data-testid="watchlist-sync-enabled"
            checked={Boolean(status?.enabled)}
            disabled={saving}
            onChange={(event) => patchSettings({ enabled: event.target.checked })}
          />
          <span>Enable sync with Plex Discover watchlist</span>
        </label>
        <label className="settings-toggle-row">
          <input
            type="checkbox"
            data-testid="watchlist-pull-on-login"
            checked={Boolean(status?.pull_on_login)}
            disabled={saving || !status?.enabled}
            onChange={(event) => patchSettings({ pull_on_login: event.target.checked })}
          />
          <span>Pull from Plex on login</span>
        </label>
        <label className="settings-toggle-row">
          <input
            type="checkbox"
            data-testid="watchlist-push-on-pin"
            checked={Boolean(status?.push_on_pin)}
            disabled={saving || !status?.enabled}
            onChange={(event) => patchSettings({ push_on_pin: event.target.checked })}
          />
          <span>Push pins to Plex when added or removed</span>
        </label>

        <div className="config-actions">
          <button
            type="button"
            data-testid="watchlist-sync-now"
            disabled={syncing || !status?.enabled}
            onClick={handleSyncNow}
          >
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>

        {Array.isArray(status?.limitations) && status.limitations.length ? (
          <ul className="settings-footnote-list" data-testid="watchlist-sync-limitations">
            {status.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {message ? (
        <p
          className={`status ${message.type === "error" ? "status-error" : ""}`}
          data-testid="watchlist-sync-message"
        >
          {message.text}
        </p>
      ) : null}
    </section>
  );
}
