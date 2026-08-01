import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  downloadLiveChannelSubtitles,
  getLiveChannelSubtitles,
  tuneLiveChannel,
} from "../../api/client";
import {
  buildOsdModel,
  classifyLiveStreamHealth,
  formatClock,
  formatWallTime,
  isHlsBufferStallDetail,
  isLivePlayerChromeTarget,
  LIVE_CC_EMPTY_STREAM,
  LIVE_STALL_ESCALATE_MS,
  liveStreamUrl,
  mergeLiveCcTracks,
  OSD_IDLE_MS,
  recordLivePlaybackDiag,
  shouldBumpOsdFromPointerMove,
  summarizeLiveVideoBuffer,
  toggleLiveVideoPlayback,
  tryPlayLiveVideo,
} from "../../lib/liveChannels.js";
import { formatLiveStreamError, liveStreamHealthCopy } from "../../lib/liveChannelsCopy.js";
import { pickLiveSoftStallPhrase } from "../../lib/liveStreamSoftStallCopy.js";
import LiveProgramHoverCard from "./LiveProgramHoverCard.jsx";

/**
 * Fullscreen-capable HLS player with cable-box OSD + subtitle picker.
 */
export default function LivePlayer({
  channel,
  channels = [],
  selectedProgram = null,
  onChannelChange,
  compact = false,
  autoFullscreen = false,
  className = "",
}) {
  const videoRef = useRef(null);
  const nextHoverLeaveTimer = useRef(null);
  const [nextHover, setNextHover] = useState(null);
  const rootRef = useRef(null);
  const hlsRef = useRef(null);
  const idleTimerRef = useRef(null);
  const pointerPosRef = useRef(null);
  const statusRef = useRef("idle");
  const waitingSinceRef = useRef(null);
  const mediaStalledRef = useRef(false);
  const hlsBufferStalledRef = useRef(false);
  const lastProgressAtRef = useRef(null);
  const lastProgressTimeRef = useRef(null);
  const lastMediaUrlRef = useRef("");
  const [osdVisible, setOsdVisible] = useState(true);
  const [osdTick, setOsdTick] = useState(Date.now());
  const [status, setStatus] = useState("idle");
  const [streamHealth, setStreamHealth] = useState("ok");
  const [softStallPhrase, setSoftStallPhrase] = useState("");
  const [error, setError] = useState("");
  const [textTracks, setTextTracks] = useState([]);
  const [activeTrack, setActiveTrack] = useState(-1);
  const [ccOpen, setCcOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const [plexCc, setPlexCc] = useState(null);
  const [ccDownloadBusy, setCcDownloadBusy] = useState(false);
  const [ccDownloadNote, setCcDownloadNote] = useState("");
  const plexTrackElRef = useRef(null);

  const channelId = channel?.id || "";
  const osd = buildOsdModel(channel, osdTick, { selectedProgram });
  const nowPlexKey = osd?.plexRatingKey || channel?.now?.plex_rating_key || "";
  const ccMerged = mergeLiveCcTracks(textTracks, plexCc);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  function diagBase(extra = {}) {
    const video = videoRef.current;
    return {
      channelId,
      mediaUrl: lastMediaUrlRef.current || liveStreamUrl(channelId),
      playbackStatus: statusRef.current,
      streamHealth,
      video: summarizeLiveVideoBuffer(video),
      ...extra,
    };
  }

  function recomputeStreamHealth(nowMs = Date.now()) {
    const video = videoRef.current;
    const waitingSince = waitingSinceRef.current;
    const waiting = waitingSince != null;
    const waitingMs = waiting ? Math.max(0, nowMs - waitingSince) : 0;
    let playheadFrozen = false;
    if (
      video
      && statusRef.current === "playing"
      && !video.paused
      && lastProgressAtRef.current != null
    ) {
      playheadFrozen = nowMs - lastProgressAtRef.current >= LIVE_STALL_ESCALATE_MS;
    }
    const next = classifyLiveStreamHealth({
      playbackStatus: statusRef.current,
      waiting,
      mediaStalled: mediaStalledRef.current,
      hlsBufferStalled: hlsBufferStalledRef.current,
      playheadFrozen,
      waitingMs,
    });
    setStreamHealth((prev) => (prev === next ? prev : next));
    if (next === "ok") {
      setSoftStallPhrase("");
    } else {
      // Lock one wry line for this soft-stall episode (no flicker on recompute).
      setSoftStallPhrase((phrase) => phrase || pickLiveSoftStallPhrase({ exclude: phrase }));
    }
    return next;
  }

  function clearStallSignals({ logEvent } = {}) {
    const had =
      waitingSinceRef.current != null
      || mediaStalledRef.current
      || hlsBufferStalledRef.current
      || streamHealth !== "ok";
    waitingSinceRef.current = null;
    mediaStalledRef.current = false;
    hlsBufferStalledRef.current = false;
    setStreamHealth("ok");
    setSoftStallPhrase("");
    if (had && logEvent) {
      recordLivePlaybackDiag(logEvent, diagBase());
    }
  }

  function bumpOsd() {
    setOsdVisible(true);
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => setOsdVisible(false), OSD_IDLE_MS);
  }

  function onPointerActivity(event) {
    const { bump, pos } = shouldBumpOsdFromPointerMove(pointerPosRef.current, event);
    pointerPosRef.current = pos;
    if (bump) bumpOsd();
  }

  useEffect(() => {
    const timer = setInterval(() => setOsdTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    let debounce = null;
    const ro = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width || 0;
      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(() => setNarrow(width < 480), 100);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (debounce) clearTimeout(debounce);
    };
  }, []);

  useEffect(() => {
    bumpOsd();
    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reveal OSD on channel change only
  }, [channelId]);

  // Richer CC: when now-playing maps to a Plex rating key, list attached tracks.
  useEffect(() => {
    if (!channelId) {
      setPlexCc(null);
      setCcDownloadNote("");
      return undefined;
    }
    let cancelled = false;
    setCcDownloadNote("");
    getLiveChannelSubtitles(channelId)
      .then((payload) => {
        if (!cancelled) setPlexCc(payload || null);
      })
      .catch(() => {
        if (!cancelled) setPlexCc(null);
      });
    return () => {
      cancelled = true;
    };
  }, [channelId, nowPlexKey]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !channelId) return undefined;

    const url = liveStreamUrl(channelId);
    lastMediaUrlRef.current = url;
    setError("");
    setStatus("loading");
    setStreamHealth("ok");
    setSoftStallPhrase("");
    waitingSinceRef.current = null;
    mediaStalledRef.current = false;
    hlsBufferStalledRef.current = false;
    lastProgressAtRef.current = null;
    lastProgressTimeRef.current = null;
    setTextTracks([]);
    setActiveTrack(-1);
    if (plexTrackElRef.current) {
      try {
        video.removeChild(plexTrackElRef.current);
      } catch {
        // ignore
      }
      plexTrackElRef.current = null;
    }
    recordLivePlaybackDiag("tune-start", {
      channelId,
      mediaUrl: url,
    });

    let destroyed = false;
    let networkRetries = 0;
    let recoverTimer = null;
    let stallNudgeTimer = null;
    const syncTracks = () => {
      if (destroyed || !video) return;
      const list = [];
      for (let i = 0; i < video.textTracks.length; i += 1) {
        const track = video.textTracks[i];
        list.push({
          index: i,
          label: track.label || track.language || `Track ${i + 1}`,
          language: track.language || "",
        });
        track.mode = i === activeTrack ? "showing" : "disabled";
      }
      setTextTracks(list);
    };

    const beginPlay = () => {
      tryPlayLiveVideo(video).then((next) => {
        if (!destroyed) {
          setStatus(next);
          if (next === "playing") {
            clearStallSignals();
            lastProgressAtRef.current = Date.now();
            lastProgressTimeRef.current = video.currentTime;
          }
        }
      });
    };

    const attachHls = () => {
      if (destroyed || !video || !Hls.isSupported()) return;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      const hls = new Hls({
        // Main-thread XHR keeps session cookies reliable on the auth’d proxy.
        enableWorker: false,
        lowLatencyMode: false,
        backBufferLength: 30,
        manifestLoadingTimeOut: 20000,
        levelLoadingTimeOut: 20000,
        fragLoadingTimeOut: 30000,
        // Auth’d stream proxy needs the session cookie on every playlist/segment.
        xhrSetup: (xhr) => {
          xhr.withCredentials = true;
        },
      });
      hlsRef.current = hls;
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (destroyed) return;
        setError("");
        recordLivePlaybackDiag("manifest-parsed", diagBase());
        beginPlay();
        syncTracks();
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (destroyed || !data) return;
        const detail = data.details || "";
        const fatal = Boolean(data.fatal);
        recordLivePlaybackDiag(fatal ? "hls-error-fatal" : "hls-error", diagBase({
          hlsType: data.type,
          hlsDetails: detail,
          fatal,
          httpCode: data.response?.code,
          fragUrl: data.frag?.url || data.url || "",
        }));
        // Non-fatal buffer underruns leave status=playing with a frozen frame —
        // surface living-room honesty + gentle startLoad nudge.
        if (!fatal) {
          if (isHlsBufferStallDetail(detail)) {
            hlsBufferStalledRef.current = true;
            if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
            recomputeStreamHealth();
            bumpOsd();
            if (!stallNudgeTimer) {
              stallNudgeTimer = setTimeout(() => {
                stallNudgeTimer = null;
                if (destroyed || !hlsRef.current) return;
                try {
                  hlsRef.current.startLoad();
                  recordLivePlaybackDiag("stall-nudge-startLoad", diagBase());
                } catch {
                  // ignore
                }
              }, LIVE_STALL_ESCALATE_MS);
            }
          }
          return;
        }
        // Soft recover without re-calling tune (tune start-over mid-watch kills Tunarr).
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR && networkRetries < 5) {
          networkRetries += 1;
          setStatus("playing");
          setError("");
          hlsBufferStalledRef.current = true;
          if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
          recomputeStreamHealth();
          bumpOsd();
          if (networkRetries <= 3) {
            hls.startLoad();
            return;
          }
          // Later retries: remount HLS against the same URL after a short pause.
          if (recoverTimer) clearTimeout(recoverTimer);
          recoverTimer = setTimeout(() => {
            if (!destroyed) attachHls();
          }, 1500 * Math.min(networkRetries, 4));
          return;
        }
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          setStatus("playing");
          setError("");
          hlsBufferStalledRef.current = true;
          if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
          recomputeStreamHealth();
          bumpOsd();
          hls.recoverMediaError();
          return;
        }
        setStatus("error");
        setStreamHealth("ok");
        setError(formatLiveStreamError(data));
      });
      hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, () => {
        // Prefer native textTracks once demuxed; also surface HLS subtitle tracks.
        const subs = hls.subtitleTracks || [];
        if (subs.length) {
          setTextTracks(
            subs.map((track, index) => ({
              index,
              label: track.name || track.lang || `CC ${index + 1}`,
              language: track.lang || "",
              viaHls: true,
            })),
          );
        } else {
          syncTracks();
        }
      });
    };

    const startPlayback = () => {
      if (destroyed || !video) return;

      if (Hls.isSupported()) {
        attachHls();
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url;
        video.addEventListener("loadedmetadata", () => {
          if (destroyed) return;
          setError("");
          beginPlay();
          syncTracks();
        });
      } else {
        setStatus("error");
        setError("HLS playback is not supported in this browser.");
      }

      if (autoFullscreen && rootRef.current?.requestFullscreen) {
        rootRef.current.requestFullscreen().catch(() => {});
      }
    };

    // Warm + start-over BEFORE loadSource so tune cannot reset the HLS session
    // out from under the first playlist/segment fetches. Mid-play recoveries
    // intentionally skip tuneLiveChannel (see attachHls error path).
    (async () => {
      try {
        await tuneLiveChannel(channelId);
      } catch (err) {
        recordLivePlaybackDiag("tune-failed", {
          channelId,
          mediaUrl: url,
          message: String(err?.message || err || "tune failed"),
        });
        // Best-effort — player still attempts the stream; errors surface via hls.js.
      }
      if (destroyed) return;
      startPlayback();
    })();

    return () => {
      destroyed = true;
      if (recoverTimer) clearTimeout(recoverTimer);
      if (stallNudgeTimer) clearTimeout(stallNudgeTimer);
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      video.removeAttribute("src");
      video.load();
    };
    // activeTrack intentionally omitted — applied in separate effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId, autoFullscreen]);

  // Detect buffer underruns / frozen playhead while status stays "playing".
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !channelId) return undefined;

    const onWaiting = () => {
      if (statusRef.current === "loading" || statusRef.current === "paused") return;
      if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
      recordLivePlaybackDiag("video-waiting", diagBase());
      recomputeStreamHealth();
      bumpOsd();
    };
    const onStalled = () => {
      if (statusRef.current === "loading" || statusRef.current === "paused") return;
      mediaStalledRef.current = true;
      if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
      recordLivePlaybackDiag("video-stalled", diagBase());
      recomputeStreamHealth();
      bumpOsd();
    };
    const onPlaying = () => {
      if (statusRef.current !== "paused" && statusRef.current !== "error") {
        setStatus("playing");
      }
      clearStallSignals({ logEvent: "video-playing" });
      lastProgressAtRef.current = Date.now();
      lastProgressTimeRef.current = video.currentTime;
    };
    const onTimeUpdate = () => {
      const t = video.currentTime;
      if (
        lastProgressTimeRef.current == null
        || Math.abs(t - lastProgressTimeRef.current) >= 0.2
      ) {
        lastProgressTimeRef.current = t;
        lastProgressAtRef.current = Date.now();
        if (
          waitingSinceRef.current != null
          || mediaStalledRef.current
          || hlsBufferStalledRef.current
        ) {
          clearStallSignals({ logEvent: "playhead-advanced" });
        }
      }
    };

    video.addEventListener("waiting", onWaiting);
    video.addEventListener("stalled", onStalled);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("timeupdate", onTimeUpdate);
    const tick = setInterval(() => {
      const health = recomputeStreamHealth();
      if (health !== "ok") bumpOsd();
    }, 1000);

    return () => {
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("stalled", onStalled);
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("timeupdate", onTimeUpdate);
      clearInterval(tick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- attach per channel tune
  }, [channelId]);

  useEffect(() => {
    const video = videoRef.current;
    const hls = hlsRef.current;
    if (!video) return;
    const plexActive = typeof activeTrack === "string" && String(activeTrack).startsWith("plex-");
    if (hls && typeof hls.subtitleTrack === "number") {
      hls.subtitleTrack = plexActive || activeTrack < 0 ? -1 : activeTrack;
    }
    for (let i = 0; i < video.textTracks.length; i += 1) {
      const track = video.textTracks[i];
      const isPlexSidecar = track?.label === "projectionist-plex-cc";
      if (plexActive && isPlexSidecar) {
        track.mode = "showing";
      } else if (!plexActive && typeof activeTrack === "number" && i === activeTrack) {
        track.mode = "showing";
      } else {
        track.mode = "disabled";
      }
    }
  }, [activeTrack]);

  function selectCcTrack(track) {
    const video = videoRef.current;
    if (!track || track.index === -1) {
      setActiveTrack(-1);
      if (video && plexTrackElRef.current) {
        try {
          video.removeChild(plexTrackElRef.current);
        } catch {
          // ignore
        }
        plexTrackElRef.current = null;
      }
      bumpOsd();
      return;
    }
    if (track.viaPlex) {
      if (!video || !track.proxyUrl) {
        setActiveTrack(-1);
        setCcDownloadNote(
          "This track is on the title in Plex. Turn on station captions in Admin so Live can carry it, or watch in Plex.",
        );
        bumpOsd();
        return;
      }
      if (plexTrackElRef.current) {
        try {
          video.removeChild(plexTrackElRef.current);
        } catch {
          // ignore
        }
        plexTrackElRef.current = null;
      }
      const el = document.createElement("track");
      el.kind = "subtitles";
      el.label = "projectionist-plex-cc";
      el.srclang = track.language || "en";
      el.src = track.proxyUrl;
      el.default = true;
      video.appendChild(el);
      plexTrackElRef.current = el;
      setActiveTrack(track.index);
      setCcDownloadNote("");
      bumpOsd();
      return;
    }
    if (video && plexTrackElRef.current) {
      try {
        video.removeChild(plexTrackElRef.current);
      } catch {
        // ignore
      }
      plexTrackElRef.current = null;
    }
    setActiveTrack(track.index);
    setCcDownloadNote("");
    bumpOsd();
  }

  async function askPlexForSubtitles() {
    if (!channelId || ccDownloadBusy) return;
    setCcDownloadBusy(true);
    setCcDownloadNote("");
    try {
      const result = await downloadLiveChannelSubtitles(channelId);
      setCcDownloadNote(result?.message || (result?.ok ? "Asked Plex for subtitles." : "Plex couldn’t find subtitles."));
      if (result?.ok) {
        const refreshed = await getLiveChannelSubtitles(channelId);
        setPlexCc(refreshed || null);
      }
    } catch (error) {
      setCcDownloadNote(error?.message || "Couldn’t ask Plex for subtitles.");
    } finally {
      setCcDownloadBusy(false);
      bumpOsd();
    }
  }

  function stepChannel(delta) {
    if (!onChannelChange || !channels.length) return;
    const idx = channels.findIndex((c) => c.id === channelId);
    const next = Math.max(0, Math.min(channels.length - 1, (idx < 0 ? 0 : idx) + delta));
    const target = channels[next];
    if (target?.id && target.id !== channelId) onChannelChange(target.id);
    bumpOsd();
  }

  function toggleFullscreen() {
    const root = rootRef.current;
    if (!root) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    } else {
      root.requestFullscreen?.().catch(() => {});
    }
    bumpOsd();
  }

  async function togglePlayback() {
    const video = videoRef.current;
    if (!video || status === "loading" || status === "error") return;
    bumpOsd();
    const wasPaused = video.paused;
    if (wasPaused) {
      // Resume segment fetching after a live pause.
      hlsRef.current?.startLoad?.();
      clearStallSignals();
    }
    const next = await toggleLiveVideoPlayback(video);
    if (next === "paused") {
      hlsRef.current?.stopLoad?.();
      clearStallSignals();
    }
    setStatus(next);
  }

  function onStageClick(event) {
    if (isLivePlayerChromeTarget(event.target)) return;
    // Only the video stage (and tap-to-play overlay) toggles — not OSD chrome.
    const onVideo = event.target === videoRef.current;
    const onGesture =
      typeof event.target?.closest === "function" &&
      event.target.closest("[data-testid='live-player-tap']");
    if (!onVideo && !onGesture) return;
    event.preventDefault();
    togglePlayback();
  }

  function onKeyDown(event) {
    const key = event.key;
    if (key === "ArrowUp") {
      event.preventDefault();
      stepChannel(-1);
    } else if (key === "ArrowDown") {
      event.preventDefault();
      stepChannel(1);
    } else if (key === " " || key === "k" || key === "K") {
      event.preventDefault();
      togglePlayback();
    } else if (key === "c" || key === "C") {
      event.preventDefault();
      setCcOpen((open) => !open);
      bumpOsd();
    } else if (key === "f" || key === "F") {
      event.preventDefault();
      toggleFullscreen();
    } else if (key === "Escape") {
      setCcOpen(false);
      bumpOsd();
    } else {
      bumpOsd();
    }
  }

  const isCompact = compact || narrow;
  const healthCopy = liveStreamHealthCopy(streamHealth, {
    phrase: softStallPhrase,
    allowPick: false,
  });
  const showOsd =
    osdVisible || ccOpen || status === "loading" || status === "error" || streamHealth !== "ok";
  const showTapHint = status === "ready" || status === "paused";
  const showHealthChip =
    Boolean(healthCopy) && status !== "loading" && status !== "error" && !error;

  return (
    <div
      ref={rootRef}
      className={`live-player${isCompact ? " live-player--compact" : ""} ${className}`.trim()}
      data-testid="live-player"
      data-channel={channelId}
      data-status={status}
      data-stream-health={streamHealth}
      tabIndex={0}
      onMouseMove={onPointerActivity}
      onFocus={bumpOsd}
      onPointerDown={onPointerActivity}
      onClick={onStageClick}
      onKeyDown={onKeyDown}
    >
      <video
        ref={videoRef}
        className="live-player-video"
        playsInline
        autoPlay
        muted={false}
        controls={false}
        data-testid="live-player-video"
      />

      {status === "loading" ? (
        <div className="live-player-status" data-testid="live-player-loading">
          <span className="live-player-spinner" aria-hidden="true" />
          <p>Tuning…</p>
        </div>
      ) : null}

      {showHealthChip ? (
        <div
          className={`live-player-status live-player-status--health${
            streamHealth === "stalled" ? " live-player-status--stalled" : ""
          }`}
          data-testid="live-player-health"
          data-health={streamHealth}
        >
          <span className="live-player-spinner" aria-hidden="true" />
          <p>{healthCopy}</p>
        </div>
      ) : null}

      {error ? (
        <div className="live-player-status live-player-status--error" data-testid="live-player-error">
          <p>{error}</p>
        </div>
      ) : null}

      {showTapHint ? (
        <div
          className="live-player-status live-player-status--gesture"
          data-testid="live-player-tap"
        >
          <p>{status === "paused" ? "Paused · tap to play" : "Tap to play"}</p>
        </div>
      ) : null}

      <div
        className={`live-osd${showOsd ? " is-visible" : ""}`}
        data-testid="live-osd"
        aria-hidden={!showOsd}
      >
        <div className="live-osd-inner">
          <div className="live-osd-channel">
            {osd?.iconUrl ? (
              <img className="live-osd-logo" src={osd.iconUrl} alt="" />
            ) : (
              <span className="live-osd-ch-num" data-testid="live-osd-number">
                {osd?.number != null ? osd.number : "—"}
              </span>
            )}
            <div className="live-osd-meta">
              <p className="live-osd-station" data-testid="live-osd-station">
                {osd?.number != null ? `${osd.number} · ` : ""}
                {osd?.name || "Channel"}
              </p>
              <h2 className="live-osd-title" data-testid="live-osd-title">
                {osd?.title || (status === "loading" ? "Tuning…" : "Nothing scheduled")}
              </h2>
              {osd?.episode && !isCompact ? (
                <p className="live-osd-episode" data-testid="live-osd-episode">
                  {osd.episode}
                </p>
              ) : null}
            </div>
            {osd?.rating ? (
              <span className="live-osd-rating" data-testid="live-osd-rating">
                {osd.rating}
              </span>
            ) : null}
          </div>

          <div className="live-osd-progress-row">
            <span data-testid="live-osd-elapsed">{formatClock(osd?.secondsElapsed)}</span>
            <div
              className="live-osd-progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(osd?.percent || 0)}
              data-testid="live-osd-progress"
            >
              <span
                className="live-osd-progress-fill"
                style={{ width: `${Math.max(0, Math.min(100, osd?.percent || 0))}%` }}
              />
            </div>
            <span data-testid="live-osd-remaining">
              {osd?.secondsRemaining != null ? `${formatClock(osd.secondsRemaining)} left` : ""}
            </span>
          </div>

          {!isCompact && (osd?.nextDisplay || osd?.nextTitle) ? (
            <p
              className="live-osd-next"
              data-testid="live-osd-next"
              onMouseEnter={(event) => {
                if (nextHoverLeaveTimer.current) {
                  clearTimeout(nextHoverLeaveTimer.current);
                  nextHoverLeaveTimer.current = null;
                }
                if (!osd?.nextProgram || osd.nextProgram.is_flex) {
                  setNextHover(null);
                  return;
                }
                const rect = event.currentTarget.getBoundingClientRect();
                setNextHover({
                  program: osd.nextProgram,
                  x: rect.left,
                  y: rect.bottom + 6,
                });
              }}
              onMouseLeave={() => {
                if (nextHoverLeaveTimer.current) clearTimeout(nextHoverLeaveTimer.current);
                nextHoverLeaveTimer.current = setTimeout(() => setNextHover(null), 160);
              }}
            >
              Next · {osd.nextDisplay || osd.nextTitle}
              {osd.nextStart ? ` · ${formatWallTime(osd.nextStart)}` : ""}
            </p>
          ) : null}
          {isCompact && (osd?.nextDisplay || osd?.nextTitle) ? (
            <p className="live-osd-next live-osd-next--compact" data-testid="live-osd-next">
              Next · {osd.nextDisplay || osd.nextTitle}
            </p>
          ) : null}

          <div className="live-osd-actions">
            <button type="button" className="ghost live-osd-btn" onClick={() => stepChannel(-1)} data-testid="live-osd-ch-up">
              Ch −
            </button>
            <button type="button" className="ghost live-osd-btn" onClick={() => stepChannel(1)} data-testid="live-osd-ch-down">
              Ch +
            </button>
            <button
              type="button"
              className="ghost live-osd-btn"
              onClick={() => {
                setCcOpen((open) => !open);
                bumpOsd();
              }}
              data-testid="live-osd-cc"
              aria-expanded={ccOpen}
            >
              CC
            </button>
            <button type="button" className="ghost live-osd-btn" onClick={toggleFullscreen} data-testid="live-osd-fs">
              Fullscreen
            </button>
          </div>

          {ccOpen ? (
            <div className="live-cc-picker" data-testid="live-cc-picker">
              <button
                type="button"
                className={`ghost live-cc-option${activeTrack === -1 ? " is-active" : ""}`}
                onClick={() => selectCcTrack({ index: -1 })}
              >
                Off
              </button>
              {ccMerged.streamTracks.map((track) => (
                <button
                  key={`stream-${track.index}`}
                  type="button"
                  className={`ghost live-cc-option${activeTrack === track.index ? " is-active" : ""}`}
                  onClick={() => selectCcTrack(track)}
                >
                  {track.label}
                </button>
              ))}
              {ccMerged.plexTracks.map((track) => (
                <button
                  key={track.index}
                  type="button"
                  className={`ghost live-cc-option${activeTrack === track.index ? " is-active" : ""}`}
                  data-testid="live-cc-plex-track"
                  onClick={() => selectCcTrack(track)}
                >
                  {track.label}
                  {track.proxyUrl ? "" : " · in Plex"}
                </button>
              ))}
              {!ccMerged.hasAny ? (
                <p className="live-cc-empty" data-testid="live-cc-unavailable">
                  {ccMerged.emptyMessage || LIVE_CC_EMPTY_STREAM}
                </p>
              ) : null}
              {ccMerged.canDownload ? (
                <button
                  type="button"
                  className="ghost live-cc-option"
                  data-testid="live-cc-ask-plex"
                  disabled={ccDownloadBusy}
                  onClick={askPlexForSubtitles}
                >
                  {ccDownloadBusy ? "Asking Plex…" : "Ask Plex for subtitles"}
                </button>
              ) : null}
              {ccDownloadNote ? (
                <p className="live-cc-empty" data-testid="live-cc-download-note">
                  {ccDownloadNote}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <LiveProgramHoverCard
        program={nextHover?.program}
        kind="next"
        open={Boolean(nextHover)}
        x={nextHover?.x || 0}
        y={nextHover?.y || 0}
        onKeepAlive={() => {
          if (nextHoverLeaveTimer.current) {
            clearTimeout(nextHoverLeaveTimer.current);
            nextHoverLeaveTimer.current = null;
          }
        }}
        onClose={() => setNextHover(null)}
      />
    </div>
  );
}
