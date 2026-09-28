import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  OSD_IDLE_MS,
  createStageGesture,
  isTheaterChromeTarget,
  skipZoneFromClientX,
  theaterHlsConfig,
} from "../../lib/theaterPlayer.js";

/**
 * Shared theater shell: auth’d HLS video, idle OSD, fullscreen, stall copy.
 * LivePlayer stays the live specialization (tune, Ch±, guide %). LibraryPlayer
 * adds VOD skip / scrub / resume on top of this shell.
 */
export default function TheaterPlayer({
  src = "",
  poster = "",
  className = "",
  testId = "theater-player",
  videoTestId = "theater-player-video",
  autoFullscreen = false,
  loading = false,
  loadingCopy = "warming the reel",
  error = "",
  errorNode = null,
  healthNode = null,
  gestureNode = null,
  osd = null,
  osdVisible: osdVisibleProp,
  onBumpOsd,
  onStatus,
  onTimeUpdate,
  onEnded,
  onPlaying,
  onWaiting,
  onStageActivate,
  onStageDoubleActivate,
  onKeyDown,
  onVideoRef,
  onHlsRef,
  children,
}) {
  const rootRef = useRef(null);
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const idleTimerRef = useRef(null);
  const pointerPosRef = useRef(null);
  const [internalOsd, setInternalOsd] = useState(true);
  const osdVisible = osdVisibleProp ?? internalOsd;

  function bumpOsd() {
    setInternalOsd(true);
    onBumpOsd?.();
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => setInternalOsd(false), OSD_IDLE_MS);
  }

  useEffect(() => {
    onVideoRef?.(videoRef.current);
    return () => onVideoRef?.(null);
  }, [onVideoRef]);

  useEffect(() => {
    bumpOsd();
    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reveal OSD when the stream changes
  }, [src]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return undefined;

    let destroyed = false;
    onStatus?.("loading");

    const attachHls = () => {
      if (destroyed || !video || !Hls.isSupported()) return;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      const hls = new Hls(theaterHlsConfig());
      hlsRef.current = hls;
      onHlsRef?.(hls);
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (destroyed) return;
        onStatus?.("ready");
        video.play?.().then(() => onStatus?.("playing")).catch(() => onStatus?.("paused"));
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (destroyed || !data?.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();
          return;
        }
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
          return;
        }
        onStatus?.("error");
      });
    };

    if (Hls.isSupported()) {
      attachHls();
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      video.addEventListener("loadedmetadata", () => {
        if (!destroyed) {
          onStatus?.("ready");
          video.play?.().then(() => onStatus?.("playing")).catch(() => onStatus?.("paused"));
        }
      });
    } else {
      onStatus?.("error");
    }

    if (autoFullscreen && rootRef.current?.requestFullscreen) {
      rootRef.current.requestFullscreen().catch(() => {});
    }

    return () => {
      destroyed = true;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
        onHlsRef?.(null);
      }
      video.removeAttribute("src");
      video.load();
    };
  }, [src, autoFullscreen, onHlsRef, onStatus]);

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

  const gesture = useRef(
    createStageGesture({
      onSingle: (event) => {
        if (isTheaterChromeTarget(event.target)) return;
        onStageActivate?.(event, zoneFromEvent(event));
      },
      onDouble: (event) => {
        if (isTheaterChromeTarget(event.target)) return;
        const zone = zoneFromEvent(event);
        if (onStageDoubleActivate) {
          onStageDoubleActivate(event, zone);
        } else if (zone === "center") {
          toggleFullscreen();
        }
      },
    }),
  );

  function zoneFromEvent(event) {
    const root = rootRef.current;
    const rect = root?.getBoundingClientRect();
    const x = event.clientX ?? event.changedTouches?.[0]?.clientX ?? 0;
    return skipZoneFromClientX(x - (rect?.left || 0), rect?.width || 0);
  }

  function handlePointerMove(event) {
    const pos = { x: event.clientX, y: event.clientY };
    const prev = pointerPosRef.current;
    pointerPosRef.current = pos;
    if (!prev || Math.abs(pos.x - prev.x) + Math.abs(pos.y - prev.y) > 4) {
      bumpOsd();
    }
  }

  function handleKeyDown(event) {
    const key = event.key;
    if (key === "f" || key === "F") {
      event.preventDefault();
      toggleFullscreen();
      return;
    }
    onKeyDown?.(event, { toggleFullscreen, bumpOsd, video: videoRef.current });
    if (key !== "Escape") bumpOsd();
  }

  return (
    <div
      ref={rootRef}
      className={`theater-player live-player ${className}`.trim()}
      data-testid={testId}
      data-osd={osdVisible ? "visible" : "hidden"}
      tabIndex={0}
      onMouseMove={handlePointerMove}
      onFocus={bumpOsd}
      onPointerDown={handlePointerMove}
      onPointerUp={(event) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        gesture.current(event);
      }}
      onKeyDown={handleKeyDown}
    >
      <video
        ref={videoRef}
        className="live-player-video theater-player-video"
        playsInline
        poster={poster || undefined}
        autoPlay
        muted={false}
        controls={false}
        data-testid={videoTestId}
        onTimeUpdate={(event) => onTimeUpdate?.(event.currentTarget)}
        onEnded={() => onEnded?.()}
        onPlaying={() => {
          onPlaying?.();
          onStatus?.("playing");
        }}
        onPause={() => onStatus?.("paused")}
        onWaiting={() => onWaiting?.()}
      />

      {loading ? (
        <div className="live-player-status theater-player-loading" data-testid={`${testId}-loading`}>
          {poster ? <img className="theater-player-poster-still" src={poster} alt="" /> : null}
          <p>{loadingCopy}</p>
        </div>
      ) : null}

      {healthNode}
      {error ? (
        errorNode || (
          <div className="live-player-status live-player-status--error" data-testid={`${testId}-error`}>
            <p>{error}</p>
          </div>
        )
      ) : null}
      {gestureNode}

      <div
        className={`live-osd theater-osd${osdVisible ? " is-visible" : ""}`}
        data-testid={`${testId}-osd`}
        aria-hidden={!osdVisible}
        data-theater-chrome="true"
      >
        {osd}
      </div>
      {children}
    </div>
  );
}

export function requestTheaterFullscreen(root) {
  if (!root) return;
  if (document.fullscreenElement) {
    document.exitFullscreen?.().catch(() => {});
  } else {
    root.requestFullscreen?.().catch(() => {});
  }
}
