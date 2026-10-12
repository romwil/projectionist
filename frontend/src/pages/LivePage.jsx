import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getLiveChannelsGuide, getPlexMachineId } from "../api/client";
import LiveGuide from "../components/live/LiveGuide";
import LivePlayer from "../components/live/LivePlayer";
import LiveTuneShare from "../components/live/LiveTuneShare";
import WeatherChannelPlayer from "../components/live/WeatherChannelPlayer";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import {
  appendWeatherChannel,
  isWeatherChannelId,
  liveGuideHref,
  liveProgramKey,
  normalizeGuide,
  popoutHandoff,
} from "../lib/liveChannels.js";
import { liveUserEmptyCopy } from "../lib/liveChannelsCopy.js";
import {
  LIVE_GUIDE_WAIT_MS,
  guideStallError,
  readLiveGuideCache,
  shouldShowGuideSkeleton,
  writeLiveGuideCache,
} from "../lib/liveGuidePaint.js";
import { saveLiveStickyOsd } from "../lib/liveTuneLink.js";
import { plexLiveTvUrl } from "../lib/titleLinks.js";

/**
 * In-app `/live` uses the shared AppShell top bar (hamburger, logo, Search,
 * Chat, Explore, and the other role-gated peers). Guide and Watch stay on
 * the Live row. The pop-out TV window keeps its own compact chrome.
 * @param {import("react").ReactNode} children
 */
function LivePlatformFrame({ children }) {
  return (
    <AppShell className="app-root live-shell" testId="live-shell" blockUntilAuth={false}>
      {children}
    </AppShell>
  );
}

/**
 * Gasp-worthy Live Channels surface: Guide ↔ Watch, auth’d HLS, pop-out TV.
 * @param {{ popout?: boolean }} props
 */
export default function LivePage({ popout = false }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const channelParam = String(searchParams.get("channel") || "").trim();
  const modeParam = String(searchParams.get("mode") || "").trim().toLowerCase();
  const weatherMode = isWeatherChannelId(channelParam) || modeParam === "weather";

  const [featureReady, setFeatureReady] = useState(false);
  const [featureOn, setFeatureOn] = useState(false);
  const [guide, setGuide] = useState(() => readLiveGuideCache());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(() => !readLiveGuideCache()?.ready);
  const [gaveUp, setGaveUp] = useState(false);
  const guideRef = useRef(guide);
  const settleTimerRef = useRef(null);
  useEffect(() => {
    guideRef.current = guide;
  }, [guide]);
  const [selectedProgram, setSelectedProgram] = useState(null);
  const [mode, setMode] = useState(() => {
    if (popout) return "watch";
    if (modeParam === "guide") return "guide";
    if (modeParam === "watch" || channelParam) return "watch";
    return "guide";
  });
  const [activeChannelId, setActiveChannelId] = useState(channelParam);
  const [plexUrl, setPlexUrl] = useState(plexLiveTvUrl());

  const loadGuide = useCallback(async ({ silent = false } = {}) => {
    if (!silent && !guideRef.current?.ready) setLoading(true);
    try {
      // The guide is server-precached (SWR). Do not wait on /api/features or
      // /api/auth/me — those can sit on SQLite's 30s busy timeout, and the
      // warming poll never starts until this request returns.
      const snapshot = await getLiveChannelsGuide({
        hours: 6,
        timeoutMs: LIVE_GUIDE_WAIT_MS,
      });
      const enabled = Boolean(snapshot?.enabled);
      setFeatureOn(enabled);
      setFeatureReady(enabled && snapshot?.reason !== "tunarr_url_missing");
      if (!enabled) {
        setGuide(null);
        setError("");
        setLoading(false);
        return;
      }
      const model = appendWeatherChannel(normalizeGuide(snapshot));
      if (model?.ready) {
        writeLiveGuideCache(model);
        setGuide(model);
        setError("");
        setActiveChannelId((current) => current || model?.channels?.[0]?.id || "");
      } else if (guideRef.current?.ready) {
        setGuide((current) => (current?.ready ? { ...current, stale: true } : current));
      } else {
        setGuide(model);
      }
      if (!silent) {
        getPlexMachineId()
          .catch(() => "")
          .then((machineId) => setPlexUrl(plexLiveTvUrl(machineId)));
      }
    } catch (err) {
      if (!guideRef.current?.ready) {
        setError(err.message || "Could not load the live guide.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGuide();
  }, [loadGuide]);

  // Hard stop. The old poll only ran after a warming payload, so a hung
  // features/auth/guide call left "Filling in the guide…" up forever.
  useEffect(() => {
    if (guide?.ready) {
      if (settleTimerRef.current) {
        clearTimeout(settleTimerRef.current);
        settleTimerRef.current = null;
      }
      return undefined;
    }
    if (settleTimerRef.current) return undefined;
    settleTimerRef.current = setTimeout(() => setGaveUp(true), LIVE_GUIDE_WAIT_MS);
    return () => {
      if (settleTimerRef.current) {
        clearTimeout(settleTimerRef.current);
        settleTimerRef.current = null;
      }
    };
  }, [guide?.ready]);

  useEffect(() => {
    if (!gaveUp || guide?.ready) return;
    // A finished "not on the air" response is not a hung guide.
    if (!loading && !guide?.warming) return;
    setLoading(false);
    setGuide((current) =>
      current?.ready ? current : current ? { ...current, warming: false, stale: false } : current,
    );
    setError((current) => current || guideStallError({ guide: null, gaveUp: true }));
  }, [gaveUp, guide?.ready, guide?.warming, loading]);

  const guideWarming = Boolean(guide?.warming);
  const guideStale = Boolean(guide?.stale);
  useEffect(() => {
    if (gaveUp || guide?.ready || (!guideWarming && !guideStale)) return undefined;
    const timer = setInterval(() => {
      loadGuide({ silent: true });
    }, 1500);
    return () => clearInterval(timer);
  }, [gaveUp, guide?.ready, guideWarming, guideStale, loadGuide]);

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

  const stallMessage = guideStallError({ guide, gaveUp, error });
  const guidePending = shouldShowGuideSkeleton({
    guide,
    error: stallMessage,
    loading,
    gaveUp,
  });
  const empty =
    !guidePending && !stallMessage && !guide?.ready
      ? liveUserEmptyCopy({
          featureOn,
          featureReady,
          guideReady: Boolean(guide?.ready),
        })
      : null;
  function withPlatformNav(node) {
    if (popout) return node;
    return <LivePlatformFrame>{node}</LivePlatformFrame>;
  }

  if (empty) {
    const ctaTo = empty.ctaTo === "admin" ? ROUTES.admin : ROUTES.chat;
    return withPlatformNav(
      <div className="live-page live-page--empty" data-testid="live-page">
        <div className="live-empty-card" data-testid={empty.testId}>
          <p className="live-eyebrow">{empty.eyebrow}</p>
          <h1>{empty.title}</h1>
          <p>{empty.body}</p>
          <Link to={ctaTo} className="btn">
            {empty.ctaLabel}
          </Link>
        </div>
      </div>,
    );
  }

  return withPlatformNav(
    <div
      className={`live-page${popout ? " live-page--popout" : ""}${mode === "watch" ? " live-page--watch" : " live-page--guide"}`}
      data-testid={popout ? "live-watch-page" : "live-page"}
      data-mode={mode}
    >
      <header className="live-chrome" data-testid="live-chrome">
        <div className="live-chrome-brand">
          {popout ? (
            <>
              <span className="live-chrome-home">Projectionist</span>
              <span className="live-chrome-sep" aria-hidden="true">
                /
              </span>
            </>
          ) : null}
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
                Watch
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

      {stallMessage ? (
        <p className="live-page-error" data-testid="live-guide-error">
          {stallMessage}
        </p>
      ) : null}

      {guidePending && !weatherMode ? (
        <div className="live-guide-skeleton" data-testid="live-guide-skeleton" aria-busy="true">
          <p className="live-page-status live-page-status--inline" data-testid="live-warming">
            Filling in the guide…
          </p>
          {Array.from({ length: 6 }, (_, row) => (
            <div key={row} className="live-guide-skeleton-row" />
          ))}
        </div>
      ) : weatherMode ? (
        <WeatherChannelPlayer
          onClose={() => {
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              next.delete("channel");
              next.set("mode", "guide");
              return next;
            });
            setMode("guide");
          }}
        />
      ) : mode === "guide" && !popout ? (
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
    </div>,
  );
}
