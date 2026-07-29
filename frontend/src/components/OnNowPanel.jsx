import { useCallback, useEffect, useState } from "react";
import { getFeatures, getLiveChannelsOnNow, getPlexMachineId } from "../api/client";
import {
  formatChannelLabel,
  formatOnNowLine,
  normalizeOnNow,
} from "../lib/onNow.js";
import { plexLiveTvUrl } from "../lib/titleLinks.js";


/** Read-only Live Channels “On now” card. CTA opens Plex — never in-app playback. */
export default function OnNowPanel({ compact = false }) {
  const [model, setModel] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [featureOn, setFeatureOn] = useState(false);
  const [plexUrl, setPlexUrl] = useState(plexLiveTvUrl());

  const load = useCallback(async () => {
    try {
      const features = await getFeatures();
      const enabled = Boolean(features?.features?.live_channels_enabled);
      setFeatureOn(enabled);
      if (!enabled) {
        setModel(null);
        setError("");
        setLoading(false);
        return;
      }
      setLoading(true);
      const [snapshot, machineId] = await Promise.all([
        getLiveChannelsOnNow(),
        getPlexMachineId().catch(() => ""),
      ]);
      setModel(normalizeOnNow(snapshot));
      setPlexUrl(plexLiveTvUrl(machineId));
      setError("");
    } catch (err) {
      setError(err.message || "Could not load what’s on now.");
      setModel(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!featureOn) {
    return null;
  }

  const channels = model?.channels?.slice(0, compact ? 4 : 8) || [];
  const showEmpty = !loading && featureOn && (!model || !model.ready);

  return (
    <section
      className={`on-now-panel${compact ? " on-now-panel--compact" : ""}`}
      data-testid="on-now-panel"
    >
      <div className="on-now-panel-head">
        <div>
          <p className="eyebrow">Live Channels</p>
          <h3 className="dash-panel-title">On now</h3>
          <p className="on-now-panel-meta">
            {model?.plexHint ||
              "Open Plex → Live TV to watch. Projectionist does not play Live Channels."}
          </p>
        </div>
        <a
          className="ghost on-now-plex-cta"
          data-testid="on-now-plex-cta"
          href={plexUrl}
          target="_blank"
          rel="noreferrer"
        >
          Open in Plex
        </a>
      </div>

      {error ? <p className="dash-panel-error">{error}</p> : null}

      {loading ? (
        <p className="status status-secondary">Checking the guide…</p>
      ) : showEmpty ? (
        <p className="dash-empty" data-testid="on-now-empty">
          Live Channels is on, but nothing is airing yet. Once stations publish,
          they’ll show up here.
        </p>
      ) : (
        <ul className="on-now-list" data-testid="on-now-list">
          {channels.map((channel) => (
            <li key={channel.id} className="on-now-row" data-testid="on-now-row">
              <span className="on-now-channel">{formatChannelLabel(channel)}</span>
              <span className="on-now-titles">{formatOnNowLine(channel)}</span>
              {channel.progressHint ? (
                <span className="on-now-progress-meta" data-testid="on-now-progress-meta">
                  {channel.progressHint}
                </span>
              ) : null}
              {channel.percent != null ? (
                <div
                  className="on-now-progress-bar"
                  role="progressbar"
                  aria-label={`${channel.nowTitle || "Program"} progress`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(channel.percent)}
                  data-testid="on-now-progress-bar"
                >
                  <span
                    className="on-now-progress-fill"
                    style={{ width: `${Math.max(0, Math.min(100, channel.percent))}%` }}
                  />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
