import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  formatApiError,
  getWatchlistSync,
  relativeTime,
  runWatchlistSync,
  updateWatchlistSync,
} from "../../api/client";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import SettingsToggle from "../../components/settings/SettingsToggle";
import { ROUTES } from "../../lib/backNav.js";

function formatSyncStats(status) {
  if (!status || status.last_pull_total == null) return null;
  const parts = [`Pulled ${status.last_pull_total}`];
  if (status.last_pull_added != null) parts.push(`added ${status.last_pull_added}`);
  if (status.last_pull_updated != null && status.last_pull_updated > 0) {
    parts.push(`updated ${status.last_pull_updated}`);
  }
  if (status.last_pull_unresolved != null && status.last_pull_unresolved > 0) {
    parts.push(`unresolved ${status.last_pull_unresolved}`);
  }
  return parts.join(" · ");
}

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
      } else if (Array.isArray(result.errors) && result.errors.length) {
        const stats = formatSyncStats(result);
        setMessage({
          type: "error",
          text: stats
            ? `Sync finished with issues — ${stats}. ${result.errors[0]}`
            : `Sync finished with issues: ${result.errors[0]}`,
        });
      } else {
        const stats = formatSyncStats(result);
        setMessage({
          type: "success",
          text: stats
            ? `Synced — ${stats}, pushed ${result.pushed ?? 0}.`
            : `Synced — pulled ${result.pulled ?? 0}, pushed ${result.pushed ?? 0}.`,
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
      <div className="settings-stack" data-testid="settings-watchlist">
        <SettingsPageHeader title="Watchlist">Loading sync status…</SettingsPageHeader>
        <p className="status status-secondary">Loading sync status…</p>
      </div>
    );
  }

  const lastSyncStats = formatSyncStats(status);

  return (
    <div className="settings-stack" data-testid="settings-watchlist">
      <SettingsPageHeader title="Watchlist" testId="settings-watchlist-header">
        Sync preferences for your Plex Discover watchlist. Browse and manage pinned titles on the{" "}
        <Link to={ROUTES.watchlist}>Watchlist page</Link>.
      </SettingsPageHeader>

      <SettingsPanel
        title="Plex Discover sync"
        lead="Uses your Sign-in-with-Plex account token to pull Discover watchlist items into CuratorX and optionally push local pins back."
        testId="watchlist-sync-panel"
        footer={
          <>
            <button
              type="button"
              data-testid="watchlist-sync-now"
              disabled={syncing || !status?.enabled}
              onClick={handleSyncNow}
            >
              {syncing ? "Syncing…" : "Sync now"}
            </button>
            <Link to={ROUTES.watchlist} className="settings-inline-link" data-testid="watchlist-open-list">
              Open watchlist
            </Link>
          </>
        }
      >
        <p className="settings-kv" data-testid="watchlist-sync-token-status">
          <span className="settings-kv-label">Token</span>
          <span>
            {status?.has_account_token
              ? "Account token on file from Sign in with Plex."
              : status?.has_plex_token
                ? status.message || "Using server Plex token (prefer Sign in with Plex)."
                : status?.message || "Re-sign in with Plex to sync your Discover watchlist."}
          </span>
        </p>
        <p className="settings-kv" data-testid="watchlist-last-synced">
          <span className="settings-kv-label">Last synced</span>
          <span>{status?.last_synced_at ? relativeTime(status.last_synced_at) : "never"}</span>
        </p>
        {lastSyncStats ? (
          <p className="settings-kv" data-testid="watchlist-last-sync-stats">
            <span className="settings-kv-label">Last pull</span>
            <span>{lastSyncStats}</span>
          </p>
        ) : null}

        <SettingsToggle
          testId="watchlist-sync-enabled"
          id="watchlist-sync-enabled"
          checked={Boolean(status?.enabled)}
          disabled={saving}
          label="Enable sync with Plex Discover watchlist"
          onChange={(value) => patchSettings({ enabled: value })}
        />
        <SettingsToggle
          testId="watchlist-pull-on-login"
          id="watchlist-pull-on-login"
          checked={Boolean(status?.pull_on_login)}
          disabled={saving || !status?.enabled}
          label="Pull from Plex on login"
          onChange={(value) => patchSettings({ pull_on_login: value })}
        />
        <SettingsToggle
          testId="watchlist-push-on-pin"
          id="watchlist-push-on-pin"
          checked={Boolean(status?.push_on_pin)}
          disabled={saving || !status?.enabled}
          label="Push pins to Plex when added or removed"
          onChange={(value) => patchSettings({ push_on_pin: value })}
        />

        {Array.isArray(status?.limitations) && status.limitations.length ? (
          <ul className="settings-footnote-list" data-testid="watchlist-sync-limitations">
            {status.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </SettingsPanel>

      {message ? (
        <p
          className={`status ${message.type === "error" ? "status-error" : ""}`}
          data-testid="watchlist-sync-message"
        >
          {message.text}
        </p>
      ) : null}
    </div>
  );
}
