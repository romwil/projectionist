import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import TuningInterstitial from "./TuningInterstitial.jsx";
import {
  OSD_IDLE_MS,
  createStageGesture,
  isTheaterChromeTarget,
  skipZoneFromClientX,
  theaterHlsConfig,
  toggleTheaterFullscreen,
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
  /** When true, show CRT static interstitial (Play seek / start waits). */
  tuning = false,
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
  // Keep parent callbacks out of the HLS effect deps. LibraryPlayer (and Live)
  // pass inline onHlsRef / onStatus — putting those in deps remounts hls.js on
  // every status tick (loading→ready→playing), which looks like: OSD flash,
  // poster still, then permanent stall with no honest error.
  const onStatusRef = useRef(onStatus);
  const onHlsRefRef = useRef(onHlsRef);
  const onVideoRefRef = useRef(onVideoRef);
  const onBumpOsdRef = useRef(onBumpOsd);
  useEffect(() => {
    onStatusRef.current = onStatus;
    onHlsRefRef.current = onHlsRef;
    onVideoRefRef.current = onVideoRef;
    onBumpOsdRef.current = onBumpOsd;
  });
  const [internalOsd, setInternalOsd] = useState(true);
  const osdVisible = osdVisibleProp ?? internalOsd;
  const showTuning = Boolean(tuning || loading);

  function bumpOsd() {
    setInternalOsd(true);
    onBumpOsdRef.current?.();
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => setInternalOsd(false), OSD_IDLE_MS);
  }

  useEffect(() => {
    onVideoRefRef.current?.(videoRef.current);
    return () => onVideoRefRef.current?.(null);
  }, []);

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
    onStatusRef.current?.("loading");

    const attachHls = () => {
      if (destroyed || !video || !Hls.isSupported()) return;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      const hls = new Hls(theaterHlsConfig());
      hlsRef.current = hls;
      onHlsRefRef.current?.(hls);
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (destroyed) return;
        onStatusRef.current?.("ready");
        video.play?.().then(() => onStatusRef.current?.("playing")).catch(() => onStatusRef.current?.("paused"));
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
        onStatusRef.current?.("error");
      });
    };

    if (Hls.isSupported()) {
      attachHls();
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      video.addEventListener("loadedmetadata", () => {
        if (!destroyed) {
          onStatusRef.current?.("ready");
          video.play?.().then(() => onStatusRef.current?.("playing")).catch(() => onStatusRef.current?.("paused"));
        }
      });
    } else {
      onStatusRef.current?.("error");
    }

    if (autoFullscreen && rootRef.current) {
      toggleTheaterFullscreen(rootRef.current);
    }

    return () => {
      destroyed = true;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
        onHlsRefRef.current?.(null);
      }
      video.removeAttribute("src");
      video.load();
    };
  }, [src, autoFullscreen]);

  function toggleFullscreen() {
    toggleTheaterFullscreen(rootRef.current);
    bumpOsd();
  }

  const gestureRef = useRef(null);
  const stageRef = useRef({
    onStageActivate,
    onStageDoubleActivate,
    toggleFullscreen,
  });
  useEffect(() => {
    stageRef.current = { onStageActivate, onStageDoubleActivate, toggleFullscreen };
  }, [onStageActivate, onStageDoubleActivate]);

  useEffect(() => {
    const handle = createStageGesture({
      onSingle: (event) => {
        if (isTheaterChromeTarget(event.target)) return;
        const zone = skipZoneFromClientX(
          (event.clientX ?? event.changedTouches?.[0]?.clientX ?? 0) -
            (rootRef.current?.getBoundingClientRect()?.left || 0),
          rootRef.current?.getBoundingClientRect()?.width || 0,
        );
        stageRef.current.onStageActivate?.(event, zone);
      },
      onDouble: (event) => {
        if (isTheaterChromeTarget(event.target)) return;
        const rect = rootRef.current?.getBoundingClientRect();
        const zone = skipZoneFromClientX(
          (event.clientX ?? event.changedTouches?.[0]?.clientX ?? 0) - (rect?.left || 0),
          rect?.width || 0,
        );
        if (stageRef.current.onStageDoubleActivate) {
          stageRef.current.onStageDoubleActivate(event, zone);
        } else if (zone === "center") {
          stageRef.current.toggleFullscreen();
        }
      },
    });
    gestureRef.current = handle;
    return () => handle.cancel?.();
  }, []);

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
        gestureRef.current?.(event);
      }}
      onKeyDown={handleKeyDown}
    >
      {/* Cover art fills the stage behind the contain video — never sizes the document. */}
      {poster ? (
        <img className="theater-stage-poster" src={poster} alt="" aria-hidden="true" data-testid={`${testId}-stage-poster`} />
      ) : null}
      <video
        ref={videoRef}
        className="live-player-video theater-player-video"
        playsInline
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

      <TuningInterstitial
        active={showTuning}
        testId={`${testId}-tuning`}
      />

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

/** @deprecated Prefer {@link toggleTheaterFullscreen} from theaterPlayer.js */
export function requestTheaterFullscreen(root) {
  toggleTheaterFullscreen(root);
}
