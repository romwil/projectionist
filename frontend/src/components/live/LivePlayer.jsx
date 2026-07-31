import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  buildOsdModel,
  formatClock,
  formatWallTime,
  liveStreamUrl,
} from "../../lib/liveChannels.js";

const OSD_IDLE_MS = 3500;

/**
 * Fullscreen-capable HLS player with cable-box OSD + subtitle picker.
 */
export default function LivePlayer({
  channel,
  channels = [],
  onChannelChange,
  compact = false,
  autoFullscreen = false,
  className = "",
}) {
  const videoRef = useRef(null);
  const rootRef = useRef(null);
  const hlsRef = useRef(null);
  const idleTimerRef = useRef(null);
  const [osdVisible, setOsdVisible] = useState(true);
  const [osdTick, setOsdTick] = useState(Date.now());
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [textTracks, setTextTracks] = useState([]);
  const [activeTrack, setActiveTrack] = useState(-1);
  const [ccOpen, setCcOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);

  const channelId = channel?.id || "";
  const osd = buildOsdModel(channel, osdTick);

  function bumpOsd() {
    setOsdVisible(true);
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => setOsdVisible(false), OSD_IDLE_MS);
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

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !channelId) return undefined;

    const url = liveStreamUrl(channelId);
    setError("");
    setStatus("loading");
    setTextTracks([]);
    setActiveTrack(-1);

    let destroyed = false;
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

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        backBufferLength: 30,
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
        setStatus("playing");
        video.play().catch(() => setStatus("ready"));
        syncTracks();
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (destroyed || !data?.fatal) return;
        setStatus("error");
        setError(data?.details || "Stream error");
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
        }
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
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url;
      video.addEventListener("loadedmetadata", () => {
        if (destroyed) return;
        setStatus("playing");
        video.play().catch(() => setStatus("ready"));
        syncTracks();
      });
    } else {
      setStatus("error");
      setError("HLS playback is not supported in this browser.");
    }

    if (autoFullscreen && rootRef.current?.requestFullscreen) {
      rootRef.current.requestFullscreen().catch(() => {});
    }

    return () => {
      destroyed = true;
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

  useEffect(() => {
    const video = videoRef.current;
    const hls = hlsRef.current;
    if (!video) return;
    if (hls && typeof hls.subtitleTrack === "number") {
      hls.subtitleTrack = activeTrack;
    }
    for (let i = 0; i < video.textTracks.length; i += 1) {
      video.textTracks[i].mode = i === activeTrack ? "showing" : "disabled";
    }
  }, [activeTrack]);

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

  function onKeyDown(event) {
    const key = event.key;
    if (key === "ArrowUp") {
      event.preventDefault();
      stepChannel(-1);
    } else if (key === "ArrowDown") {
      event.preventDefault();
      stepChannel(1);
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
  const showOsd = osdVisible || ccOpen || status === "loading" || status === "error";

  return (
    <div
      ref={rootRef}
      className={`live-player${isCompact ? " live-player--compact" : ""} ${className}`.trim()}
      data-testid="live-player"
      data-channel={channelId}
      tabIndex={0}
      onMouseMove={bumpOsd}
      onFocus={bumpOsd}
      onPointerDown={bumpOsd}
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

      {error ? (
        <div className="live-player-status live-player-status--error" data-testid="live-player-error">
          <p>{error}</p>
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

          {!isCompact && osd?.nextTitle ? (
            <p className="live-osd-next" data-testid="live-osd-next">
              Next · {osd.nextTitle}
              {osd.nextStart ? ` · ${formatWallTime(osd.nextStart)}` : ""}
            </p>
          ) : null}
          {isCompact && osd?.nextTitle ? (
            <p className="live-osd-next live-osd-next--compact" data-testid="live-osd-next">
              Next · {osd.nextTitle}
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
                className={`ghost live-cc-option${activeTrack < 0 ? " is-active" : ""}`}
                onClick={() => setActiveTrack(-1)}
              >
                Off
              </button>
              {textTracks.length ? (
                textTracks.map((track) => (
                  <button
                    key={track.index}
                    type="button"
                    className={`ghost live-cc-option${activeTrack === track.index ? " is-active" : ""}`}
                    onClick={() => setActiveTrack(track.index)}
                  >
                    {track.label}
                  </button>
                ))
              ) : (
                <p className="live-cc-empty" data-testid="live-cc-unavailable">
                  No subtitles on this stream
                </p>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
