import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  getFeatures,
  getLiveChannelsGuide,
  getPlexMachineId,
} from "../api/client";
import LiveGuide from "../components/live/LiveGuide";
import LivePlayer from "../components/live/LivePlayer";
import LiveTuneShare from "../components/live/LiveTuneShare";
import { useAuthGate } from "../components/UserMenu";
import { ROUTES } from "../lib/backNav.js";
import {
  liveGuideHref,
  liveProgramKey,
  normalizeGuide,
  popoutHandoff,
} from "../lib/liveChannels.js";
import { liveUserEmptyCopy } from "../lib/liveChannelsCopy.js";
import { saveLiveStickyOsd } from "../lib/liveTuneLink.js";
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
  const [selectedProgram, setSelectedProgram] = useState(null);
  const [mode, setMode] = useState(() => {
    if (popout) return "watch";
    if (modeParam === "guide") return "guide";
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
    if (popout) return;
    if (modeParam === "guide") setMode("guide");
    else if (modeParam === "watch") setMode("watch");
  }, [modeParam, popout]);

  useEffect(() => {
    if (channelParam && channelParam !== activeChannelId) {
      setActiveChannelId(channelParam);
      setSelectedProgram(null);
      if (!popout && modeParam !== "guide") setMode("watch");
    }
  }, [channelParam, activeChannelId, popout, modeParam]);

  const channels = guide?.channels || [];
  const activeChannel = useMemo(
    () => channels.find((c) => c.id === activeChannelId) || channels[0] || null,
    [channels, activeChannelId],
  );

  function handleTune(channelId, program = null) {
    const id = String(channelId || "").trim();
    if (!id) return;
    // LivePlayer warms Tunarr before loadSource — do not race tune here.
    setActiveChannelId(id);
    setSelectedProgram(program && typeof program === "object" ? program : null);
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
  }

  function handleChannelChange(channelId) {
    // Ch+/Ch− clears guide-cell selection so OSD follows wall-clock again.
    handleTune(channelId, null);
  }

  const selectedProgramKey = liveProgramKey(activeChannel?.id || activeChannelId, selectedProgram);

  useEffect(() => {
    if (!activeChannel?.id || mode !== "watch") return;
    const nowTitle = String(
      selectedProgram?.title || activeChannel?.now?.title || "",
    ).trim();
    saveLiveStickyOsd({
      channelId: activeChannel.id,
      channelName: String(activeChannel.name || "Live"),
      nowTitle,
    });
    window.dispatchEvent(new Event("projectionist:live-sticky"));
  }, [activeChannel, mode, selectedProgram]);

  function openPopout() {
    const channelId = activeChannel?.id || activeChannelId;
    const { popoutHref } = popoutHandoff(channelId);
    const features =
      "popup=yes,width=960,height=540,menubar=no,toolbar=no,location=no,status=no";
    // Must open synchronously inside the click gesture (popup blockers).
    const popup = window.open(popoutHref, "projectionist-live-tv", features);
    if (!popup) return;
    // Hand off: unload opener LivePlayer so only the pop-out holds the Tunarr session.
    setMode("guide");
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        const id = String(channelId || "").trim();
        if (id) next.set("channel", id);
        next.set("mode", "guide");
        return next;
      },
      { replace: true },
    );
  }

  function goGuideMode() {
    setMode("guide");
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("mode", "guide");
        return next;
      },
      { replace: true },
    );
  }

  if (!authReady || loading) {
    return (
      <div className="live-page live-page--loading" data-testid="live-page">
        <p className="live-page-status">Loading Live…</p>
      </div>
    );
  }

  const empty = liveUserEmptyCopy({
    featureOn,
    featureReady,
    guideReady: Boolean(guide?.ready),
  });
  if (empty) {
    const ctaTo = empty.ctaTo === "admin" ? ROUTES.admin : ROUTES.chat;
    return (
      <div className="live-page live-page--empty" data-testid="live-page">
        <div className="live-empty-card" data-testid={empty.testId}>
          <p className="live-eyebrow">{empty.eyebrow}</p>
          <h1>{empty.title}</h1>
          <p>{empty.body}</p>
          <Link to={ctaTo} className="btn">
            {empty.ctaLabel}
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
                onClick={() => goGuideMode()}
              >
                Guide
              </button>
              <button
                type="button"
                className={mode === "watch" ? "is-active" : ""}
                data-testid="live-mode-watch"
                onClick={() => activeChannel && handleTune(activeChannel.id)}
              >
                Watch here
              </button>
            </div>
          ) : (
            <Link
              to={liveGuideHref(activeChannel?.id)}
              className="ghost live-chrome-link"
              data-testid="live-open-guide"
              onClick={(event) => {
                // Prefer focusing an existing /live tab when possible.
                if (window.opener && !window.opener.closed) {
                  event.preventDefault();
                  window.opener.focus();
                  try {
                    window.opener.location.href = liveGuideHref(activeChannel?.id);
                  } catch {
                    navigate(ROUTES.live);
                  }
                }
              }}
            >
              Guide
            </Link>
          )}

          <div className="live-chrome-secondary" role="group" aria-label="Also watch">
            {!popout ? (
              <LiveTuneShare
                channelId={activeChannel?.id || activeChannelId}
                channelName={activeChannel?.name || ""}
              />
            ) : null}
            {!popout ? (
              <button
                type="button"
                className="live-chrome-icon-btn"
                data-testid="live-popout"
                onClick={openPopout}
                disabled={!activeChannel}
                aria-label="Pop out TV window"
                data-tooltip="Pop out"
                title="Pop out"
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  open_in_new
                </span>
              </button>
            ) : null}

            <a
              className="live-chrome-icon-btn"
              href={plexUrl}
              target="_blank"
              rel="noreferrer"
              data-testid="live-plex-secondary"
              aria-label="Also in Plex Live TV — same stations, living-room apps"
              data-tooltip="Plex Live TV"
              title="Also in Plex Live TV — same stations, living-room apps"
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                live_tv
              </span>
            </a>
          </div>
        </div>
      </header>

      {error ? <p className="live-page-error">{error}</p> : null}

      {mode === "guide" && !popout ? (
        <LiveGuide
          guide={guide}
          selectedChannelId={activeChannel?.id || ""}
          selectedProgramKey={selectedProgramKey}
          onSelectChannel={setActiveChannelId}
          onTune={(id, program) => handleTune(id, program)}
        />
      ) : (
        <LivePlayer
          channel={activeChannel}
          channels={channels}
          selectedProgram={selectedProgram}
          onChannelChange={handleChannelChange}
          compact={popout}
        />
      )}
    </div>
  );
}
