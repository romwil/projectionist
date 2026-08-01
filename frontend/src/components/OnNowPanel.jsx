import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getFeatures, getLiveChannelsOnNow, getPlexMachineId } from "../api/client";
import { ROUTES } from "../lib/backNav.js";
import { liveWatchHref } from "../lib/liveChannels.js";
import {
  formatChannelLabel,
  formatOnNowLine,
  normalizeOnNow,
  visibleOnNowChannels,
} from "../lib/onNow.js";
import { plexLiveTvUrl } from "../lib/titleLinks.js";

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

  const channels = visibleOnNowChannels(model?.channels, { compact });
  const totalChannels = Array.isArray(model?.channels) ? model.channels.length : 0;
  const showEmpty = !loading && featureOn && (!model || !model.ready);
  const firstChannelId = channels[0]?.id || "";

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
              "Watch here or in Plex Live TV — same stations, both first-class."}
          </p>
        </div>
        <div className="on-now-cta-row">
          <Link
            className="btn on-now-watch-cta"
            data-testid="on-now-watch-cta"
            to={liveWatchHref(firstChannelId)}
          >
            Watch here
          </Link>
          <a
            className="ghost on-now-plex-cta"
            data-testid="on-now-plex-cta"
            href={plexUrl}
            target="_blank"
            rel="noreferrer"
          >
            Also in Plex Live TV
          </a>
          {totalChannels > 0 ? (
            <Link className="ghost on-now-see-all" data-testid="on-now-see-all" to={ROUTES.live}>
              See all
            </Link>
          ) : null}
        </div>
      </div>

      {error ? <p className="dash-panel-error">{error}</p> : null}

      {loading ? (
        <p className="status status-secondary">Checking the guide…</p>
      ) : showEmpty ? (
        <p className="dash-empty" data-testid="on-now-empty">
          Live is on, but nothing is airing yet. Once something’s on, it’ll show
          up here.
        </p>
      ) : (
        <ul className="on-now-list" data-testid="on-now-list">
          {channels.map((channel) => (
            <li key={channel.id} className="on-now-row" data-testid="on-now-row">
              <Link
                className="on-now-row-link"
                to={liveWatchHref(channel.id)}
                data-testid="on-now-row-link"
              >
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
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
