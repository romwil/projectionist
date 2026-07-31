import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  getFeatures,
  getLiveChannelsGuide,
  getPlexMachineId,
  tuneLiveChannel,
} from "../api/client";
import LiveGuide from "../components/live/LiveGuide";
import LivePlayer from "../components/live/LivePlayer";
import { useAuthGate } from "../components/UserMenu";
import { ROUTES } from "../lib/backNav.js";
import { liveWatchHref, normalizeGuide } from "../lib/liveChannels.js";
import { plexLiveTvUrl } from "../lib/titleLinks.js";

/**
 * Gasp-worthy Live Channels surface: Guide ↔ Watch, auth’d HLS, pop-out TV.
 * @param {{ popout?: boolean }} props
 */
export default function LivePage({ popout = false }) {
  const { authReady } = useAuthGate();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const channelParam = String(searchParams.get("channel") || "").trim();
  const modeParam = String(searchParams.get("mode") || "").trim().toLowerCase();

  const [featureReady, setFeatureReady] = useState(false);
  const [featureOn, setFeatureOn] = useState(false);
  const [guide, setGuide] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tuning, setTuning] = useState(false);
  const [mode, setMode] = useState(() => {
    if (popout) return "watch";
    if (modeParam === "watch" || channelParam) return "watch";
    return "guide";
  });
  const [activeChannelId, setActiveChannelId] = useState(channelParam);
  const [plexUrl, setPlexUrl] = useState(plexLiveTvUrl());

  const loadGuide = useCallback(async () => {
    setLoading(true);
    try {
      const features = await getFeatures();
      const enabled = Boolean(features?.features?.live_channels_enabled);
      const ready = Boolean(features?.features?.live_channels_ready);
      setFeatureOn(enabled);
      setFeatureReady(ready);
      if (!enabled) {
        setGuide(null);
        setError("");
        setLoading(false);
        return;
      }
      const [snapshot, machineId] = await Promise.all([
        getLiveChannelsGuide({ hours: 6 }),
        getPlexMachineId().catch(() => ""),
      ]);
      const model = normalizeGuide(snapshot);
      setGuide(model);
      setPlexUrl(plexLiveTvUrl(machineId));
      setError("");
      setActiveChannelId((current) => current || model?.channels?.[0]?.id || "");
    } catch (err) {
      setError(err.message || "Could not load the live guide.");
      setGuide(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authReady) return;
    loadGuide();
  }, [authReady, loadGuide]);

  useEffect(() => {
    if (channelParam && channelParam !== activeChannelId) {
      setActiveChannelId(channelParam);
      if (!popout) setMode("watch");
    }
  }, [channelParam, activeChannelId, popout]);

  const channels = guide?.channels || [];
  const activeChannel = useMemo(
    () => channels.find((c) => c.id === activeChannelId) || channels[0] || null,
    [channels, activeChannelId],
  );

  async function handleTune(channelId) {
    const id = String(channelId || "").trim();
    if (!id) return;
    setActiveChannelId(id);
    setMode("watch");
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("channel", id);
        next.set("mode", "watch");
        return next;
      },
      { replace: true },
    );
    setTuning(true);
    try {
      await tuneLiveChannel(id);
    } catch {
      // Player still attempts the stream; warm is best-effort.
    } finally {
      setTuning(false);
    }
  }

  function handleChannelChange(channelId) {
    handleTune(channelId);
  }

  function openPopout() {
    const href = liveWatchHref(activeChannel?.id || activeChannelId, { popout: true });
    const features =
      "popup=yes,width=960,height=540,menubar=no,toolbar=no,location=no,status=no";
    window.open(href, "projectionist-live-tv", features);
  }

  if (!authReady || loading) {
    return (
      <div className="live-page live-page--loading" data-testid="live-page">
        <p className="live-page-status">Loading Live…</p>
      </div>
    );
  }

  if (!featureOn) {
    return (
      <div className="live-page live-page--empty" data-testid="live-page">
        <div className="live-empty-card">
          <p className="live-eyebrow">Live Channels</p>
          <h1>Not on the air yet</h1>
          <p>Ask the household owner to enable Live Channels in Admin.</p>
          <Link to={ROUTES.chat} className="btn">
            Back to chat
          </Link>
        </div>
      </div>
    );
  }

  if (!featureReady && !guide?.ready) {
    return (
      <div className="live-page live-page--empty" data-testid="live-page">
        <div className="live-empty-card">
          <p className="live-eyebrow">Live Channels</p>
          <h1>Broadcast engine warming</h1>
          <p>Stations appear here once Tunarr is reachable and published.</p>
          <Link to={ROUTES.admin} className="btn">
            Open Admin
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`live-page${popout ? " live-page--popout" : ""}${mode === "watch" ? " live-page--watch" : " live-page--guide"}`}
      data-testid={popout ? "live-watch-page" : "live-page"}
      data-mode={mode}
    >
      <header className="live-chrome" data-testid="live-chrome">
        <div className="live-chrome-brand">
          {!popout ? (
            <Link to={ROUTES.chat} className="live-chrome-home" data-testid="live-back-chat">
              Projectionist
            </Link>
          ) : (
            <span className="live-chrome-home">Projectionist</span>
          )}
          <span className="live-chrome-sep" aria-hidden="true">
            /
          </span>
          <h1 className="live-chrome-title">Live</h1>
        </div>

        <div className="live-chrome-actions">
          {!popout ? (
            <div className="live-mode-toggle" role="group" aria-label="Guide or Watch">
              <button
                type="button"
                className={mode === "guide" ? "is-active" : ""}
                data-testid="live-mode-guide"
                onClick={() => setMode("guide")}
              >
                Guide
              </button>
              <button
                type="button"
                className={mode === "watch" ? "is-active" : ""}
                data-testid="live-mode-watch"
                onClick={() => activeChannel && handleTune(activeChannel.id)}
              >
                Watch
              </button>
            </div>
          ) : (
            <Link
              to={liveWatchHref(activeChannel?.id, { popout: false })}
              className="ghost live-chrome-link"
              data-testid="live-open-guide"
              onClick={(event) => {
                // Prefer focusing an existing /live tab when possible.
                if (window.opener && !window.opener.closed) {
                  event.preventDefault();
                  window.opener.focus();
                  try {
                    window.opener.location.href = liveWatchHref(activeChannel?.id);
                  } catch {
                    navigate(ROUTES.live);
                  }
                }
              }}
            >
              Guide
            </Link>
          )}

          {!popout ? (
            <button
              type="button"
              className="ghost"
              data-testid="live-popout"
              onClick={openPopout}
              disabled={!activeChannel}
            >
              Pop out
            </button>
          ) : null}

          <a
            className="ghost live-chrome-link"
            href={plexUrl}
            target="_blank"
            rel="noreferrer"
            data-testid="live-plex-secondary"
          >
            Open in Plex Live TV
          </a>
        </div>
      </header>

      {error ? <p className="live-page-error">{error}</p> : null}
      {tuning ? (
        <p className="live-page-status live-page-status--inline" data-testid="live-tuning">
          Warming stream…
        </p>
      ) : null}

      {mode === "guide" && !popout ? (
        <LiveGuide
          guide={guide}
          selectedChannelId={activeChannel?.id || ""}
          onSelectChannel={setActiveChannelId}
          onTune={(id) => handleTune(id)}
        />
      ) : (
        <LivePlayer
          channel={activeChannel}
          channels={channels}
          onChannelChange={handleChannelChange}
          compact={popout}
        />
      )}
    </div>
  );
}
