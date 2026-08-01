import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLiveChannelsStatus } from "../api/client";
import { ROUTES } from "../lib/backNav.js";
import { liveWatchHref } from "../lib/liveChannels.js";
import { formatChannelLabel } from "../lib/onNow.js";
import { normalizeOwnerNowPlaying } from "../lib/ownerNowPlaying.js";

const POLL_MS = 20_000;

/**
 * Owner ops-grade “What’s currently playing” — all stations, progress, next wall
 * time, health. Admin Overview + Live Channels → Stations.
 */
export default function OwnerNowPlayingBreakdown({
  status: statusProp = null,
  onRefreshStatus = null,
  onOpenStationSettings = null,
  poll = true,
  compact = false,
}) {
  const [status, setStatus] = useState(statusProp);
  const [loading, setLoading] = useState(!statusProp);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (typeof onRefreshStatus === "function") {
      try {
        await onRefreshStatus();
        setError("");
      } catch (err) {
        setError(err.message || "Could not refresh now playing.");
      }
      return;
    }
    setLoading(true);
    try {
      const next = await getLiveChannelsStatus();
      setStatus(next);
      setError("");
    } catch (err) {
      setError(err.message || "Could not load now playing.");
    } finally {
      setLoading(false);
    }
  }, [onRefreshStatus]);

  useEffect(() => {
    if (statusProp) {
      setStatus(statusProp);
      setLoading(false);
    }
  }, [statusProp]);

  useEffect(() => {
    if (statusProp && typeof onRefreshStatus !== "function") return undefined;
    if (!statusProp) {
      load();
    }
    if (!poll) return undefined;
    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      load();
    };
    const id = setInterval(tick, POLL_MS);
    return () => clearInterval(id);
  }, [load, poll, statusProp, onRefreshStatus]);

  const model = normalizeOwnerNowPlaying(status);
  if (!model.enabled && !loading) {
    return null;
  }

  return (
    <section
      className={`owner-now-playing${compact ? " owner-now-playing--compact" : ""}`}
      data-testid="owner-now-playing"
    >
      <div className="owner-now-playing-head">
        <div>
          <p className="eyebrow">Live Channels</p>
          <h3 className="dash-panel-title">What’s currently playing</h3>
          <p className="owner-now-playing-meta">
            All stations — now, progress, next wall time, and health. Dig in to Watch,
            Guide, or station settings.
          </p>
        </div>
        <button
          type="button"
          className="ghost"
          data-testid="owner-now-playing-refresh"
          onClick={() => load()}
        >
          Refresh
        </button>
      </div>

      {error ? <p className="dash-panel-error">{error}</p> : null}
      {loading && !model.rows.length ? (
        <p className="status status-secondary">Checking every station…</p>
      ) : null}

      {!loading && model.rows.length === 0 ? (
        <p className="dash-empty" data-testid="owner-now-playing-empty">
          {model.engineUp
            ? "TV engine is up, but no stations are listed yet."
            : "TV engine unreachable — open Live Channels Setup to reconnect."}
        </p>
      ) : null}

      {model.rows.length ? (
        <div className="owner-now-playing-table-wrap">
          <table className="owner-now-playing-table" data-testid="owner-now-playing-table">
            <thead>
              <tr>
                <th scope="col">Station</th>
                <th scope="col">Now</th>
                <th scope="col">Next</th>
                <th scope="col">Health</th>
                <th scope="col">Dig in</th>
              </tr>
            </thead>
            <tbody>
              {model.rows.map((row) => (
                <tr key={row.id} data-testid="owner-now-playing-row">
                  <td data-label="Station">
                    <span className="owner-now-playing-station">
                      {formatChannelLabel(row)}
                    </span>
                  </td>
                  <td data-label="Now">
                    <span className="owner-now-playing-now">
                      {row.nowTitle || "—"}
                    </span>
                    {row.progressHint ? (
                      <span className="owner-now-playing-progress" data-testid="owner-now-playing-progress">
                        {row.progressHint}
                      </span>
                    ) : null}
                    {row.airingWhy ? (
                      <span className="owner-now-playing-why" data-testid="owner-now-playing-why">
                        {row.airingWhy}
                      </span>
                    ) : null}
                    {row.percent != null ? (
                      <div
                        className="on-now-progress-bar"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={Math.round(row.percent)}
                      >
                        <span
                          className="on-now-progress-fill"
                          style={{ width: `${Math.max(0, Math.min(100, row.percent))}%` }}
                        />
                      </div>
                    ) : null}
                    {row.warning === "padded_stop" ? (
                      <span className="owner-now-playing-warn" data-testid="owner-now-playing-warn">
                        Guide stop overruns next start
                      </span>
                    ) : null}
                  </td>
                  <td data-label="Next">
                    {row.nextTitle ? (
                      <span className="owner-now-playing-next">
                        {row.nextTitle}
                        {row.nextWall ? (
                          <span className="owner-now-playing-wall"> · {row.nextWall}</span>
                        ) : null}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td data-label="Health">
                    <span
                      className={`owner-now-playing-health health-${row.health || "idle"}`}
                      data-testid="owner-now-playing-health"
                    >
                      {row.healthLabel || "—"}
                      {row.streamConnections > 0
                        ? ` · ${row.streamConnections} stream${row.streamConnections === 1 ? "" : "s"}`
                        : ""}
                    </span>
                  </td>
                  <td data-label="Dig in">
                    <div className="owner-now-playing-actions">
                      <Link
                        className="ghost"
                        to={liveWatchHref(row.id)}
                        data-testid="owner-now-playing-watch"
                      >
                        Watch
                      </Link>
                      <Link
                        className="ghost"
                        to={ROUTES.live}
                        data-testid="owner-now-playing-guide"
                      >
                        Guide
                      </Link>
                      {typeof onOpenStationSettings === "function" ? (
                        <button
                          type="button"
                          className="ghost"
                          data-testid="owner-now-playing-settings"
                          onClick={() => onOpenStationSettings(row.id)}
                        >
                          Settings
                        </button>
                      ) : (
                        <Link
                          className="ghost"
                          to="/admin/live-channels"
                          data-testid="owner-now-playing-admin"
                        >
                          Stations
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
