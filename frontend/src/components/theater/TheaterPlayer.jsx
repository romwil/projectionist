import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { LIVE_STALL_ESCALATE_MS, LIVE_STALL_NOTICE_MS } from "../../lib/liveChannels.js";
import BufferingIndicator from "./BufferingIndicator.jsx";
import TuningInterstitial from "./TuningInterstitial.jsx";
import {
  OSD_IDLE_MS,
  applyHoldPlaybackRate,
  bottomThirdTapResult,
  clearTheaterTextSelection,
  createStageGesture,
  dispatchPictureTap,
  holdToRateShouldCancelTap,
  isTheaterChromeTarget,
  libraryBufferingCopy,
  libraryBufferingHealth,
  pictureTapIntent,
  restoreHoldPlaybackRate,
  shouldRevealPlaybackPicture,
  shouldShowHoldRateChip,
  shouldShowLibraryBufferingChip,
  skipZoneFromClientX,
  stepLibraryBufferingUi,
  suppressHoldTextSelection,
  playStageChrome,
  theaterHlsConfig,
  toggleTheaterFullscreen,
} from "../../lib/theaterPlayer.js";
import { silenceNativeTextTracks } from "../../lib/subtitleCues.js";
import { playShrunkAfterReload } from "../../lib/inAppPip.js";

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
  /** When true, show CRT static interstitial (Play start / Live tune). */
  tuning = false,
  /**
   * Session-restart seek: hide the video element until the new playlist
   * can paint. `holdFrame` is the previous picture (or empty for the poster).
   */
  pictureHold = false,
  holdFrame = "",
  onPictureReady,
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
  onOsdVisibility,
  pausedFrameClean = false,
  /** After a shrunk-play reload, start muted if unmuted autoplay is blocked. */
  resumeMutedIfBlocked = false,
  onAutoplayResult,
  /** Library Play only: press-and-hold 2x. Live TV must leave this false. */
  holdToDoubleSpeed = false,
  /** Library Play: hide the blurred poster border and use a black letterbox. */
  blackFrame = false,
  /** Library Play only: delayed buffering OSD. Live has its own chips. */
  bufferingEnabled = false,
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
  const onOsdVisibilityRef = useRef(onOsdVisibility);
  const onPictureReadyRef = useRef(onPictureReady);
  const pictureHoldRef = useRef(pictureHold);
  const resumeMutedIfBlockedRef = useRef(resumeMutedIfBlocked);
  const onAutoplayResultRef = useRef(onAutoplayResult);
  const holdToDoubleSpeedRef = useRef(holdToDoubleSpeed);
  const bufferingEnabledRef = useRef(bufferingEnabled);
  const bottomTapRef = useRef(null);
  const holdRef = useRef({ active: false, downAt: 0 });
  const waitingSinceRef = useRef(null);
  const bufferUiRef = useRef({ displayed: "ok", stickyUntil: null });
  const bufferTimerRef = useRef(null);
  const [holdRateOn, setHoldRateOn] = useState(false);
  const [bufferUi, setBufferUi] = useState({ displayed: "ok", stickyUntil: null });
  useEffect(() => {
    onStatusRef.current = onStatus;
    onHlsRefRef.current = onHlsRef;
    onVideoRefRef.current = onVideoRef;
    onBumpOsdRef.current = onBumpOsd;
    onOsdVisibilityRef.current = onOsdVisibility;
    onPictureReadyRef.current = onPictureReady;
    pictureHoldRef.current = pictureHold;
    resumeMutedIfBlockedRef.current = resumeMutedIfBlocked;
    onAutoplayResultRef.current = onAutoplayResult;
    holdToDoubleSpeedRef.current = holdToDoubleSpeed;
    bufferingEnabledRef.current = bufferingEnabled;
  });
  const [internalOsd, setInternalOsd] = useState(true);
  const osdVisible = osdVisibleProp ?? internalOsd;
  const showTuning = Boolean(tuning || loading);

  function hideOsd() {
    setInternalOsd(false);
    onOsdVisibilityRef.current?.(false);
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
  }

  function bumpOsd() {
    setInternalOsd(true);
    onOsdVisibilityRef.current?.(true);
    onBumpOsdRef.current?.();
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => hideOsd(), OSD_IDLE_MS);
  }

  function applyBottomThird() {
    const result = bottomThirdTapResult({
      visibleAtPointerDown: Boolean(bottomTapRef.current?.visibleAtPointerDown),
    });
    if (result.effect === "hide") hideOsd();
    else bumpOsd();
  }

  function syncHoldChip() {
    setHoldRateOn(shouldShowHoldRateChip(videoRef.current?.playbackRate));
  }

  function startHoldToRate() {
    if (!holdToDoubleSpeedRef.current) return false;
    const video = videoRef.current;
    if (!video || video.paused || video.ended) return false;
    holdRef.current = { active: true, downAt: Date.now() };
    clearTheaterTextSelection();
    applyHoldPlaybackRate(video);
    syncHoldChip();
    return true;
  }

  function endHoldToRate() {
    if (!holdRef.current.active) return { held: false, downAt: 0 };
    const downAt = holdRef.current.downAt;
    holdRef.current = { active: false, downAt: 0 };
    restoreHoldPlaybackRate(videoRef.current);
    syncHoldChip();
    return { held: true, downAt };
  }

  function refreshBufferHealth({ mediaStalled = false } = {}) {
    if (!bufferingEnabledRef.current) {
      waitingSinceRef.current = null;
      bufferUiRef.current = { displayed: "ok", stickyUntil: null };
      setBufferUi(bufferUiRef.current);
      return;
    }
    const video = videoRef.current;
    const nowMs = Date.now();
    const waitingSince = waitingSinceRef.current;
    const waiting = waitingSince != null;
    const waitingMs = waiting ? Math.max(0, nowMs - waitingSince) : 0;
    const paused = Boolean(video?.paused && !video?.ended);
    const raw = libraryBufferingHealth({
      playbackStatus: showTuning || paused ? (paused ? "paused" : "loading") : "playing",
      waiting: waiting || Boolean(pictureHoldRef.current),
      mediaStalled,
      waitingMs,
    });
    const next = stepLibraryBufferingUi(bufferUiRef.current, { rawHealth: raw, nowMs });
    bufferUiRef.current = next;
    setBufferUi(next);
    if (bufferTimerRef.current) {
      window.clearTimeout(bufferTimerRef.current);
      bufferTimerRef.current = null;
    }
    if (waiting && (next.displayed === "ok" || next.displayed === "buffering")) {
      const edge = next.displayed === "ok" ? LIVE_STALL_NOTICE_MS : LIVE_STALL_ESCALATE_MS;
      const delay = Math.max(0, edge - waitingMs);
      bufferTimerRef.current = window.setTimeout(() => refreshBufferHealth(), delay + 16);
    }
  }

  function noteWaiting() {
    if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
    refreshBufferHealth();
  }

  function notePlayingFrame() {
    const video = videoRef.current;
    if (
      shouldRevealPlaybackPicture({
        holdingSeek: false,
        readyState: video?.readyState ?? 0,
        videoWidth: video?.videoWidth ?? 0,
      })
    ) {
      waitingSinceRef.current = null;
    }
    refreshBufferHealth();
  }

  useEffect(() => {
    onVideoRefRef.current?.(videoRef.current);
    return () => onVideoRefRef.current?.(null);
  }, []);

  useLayoutEffect(() => {
    const video = videoRef.current;
    if (video?.dataset?.shrunkHoldMute === "1") video.muted = true;
  });

  useEffect(() => {
    bumpOsd();
    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      if (bufferTimerRef.current) window.clearTimeout(bufferTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reveal OSD when the stream changes
  }, [src]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return undefined;

    let destroyed = false;
    onStatusRef.current?.("loading");

    const startAutoplay = () => {
      if (resumeMutedIfBlockedRef.current) {
        playShrunkAfterReload(video).then((result) => {
          if (destroyed) return;
          onAutoplayResultRef.current?.(result);
          onStatusRef.current?.(result.playing ? "playing" : "paused");
        });
        return;
      }
      video.play?.().then(() => onStatusRef.current?.("playing")).catch(() => onStatusRef.current?.("paused"));
    };

    const muteNativeSubs = () => {
      if (destroyed) return;
      const hls = hlsRef.current;
      if (hls && typeof hls.subtitleTrack === "number") hls.subtitleTrack = -1;
      silenceNativeTextTracks(video);
    };

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
        muteNativeSubs();
        onStatusRef.current?.("ready");
        startAutoplay();
      });
      hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, muteNativeSubs);
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (destroyed || !data?.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();
          return;
        }
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          // A seek hold must not recover into a snow frame with live audio.
          if (pictureHoldRef.current) {
            onStatusRef.current?.("error");
            return;
          }
          hls.recoverMediaError();
          return;
        }
        onStatusRef.current?.("error");
      });
    };

    video.textTracks?.addEventListener?.("addtrack", muteNativeSubs);

    if (Hls.isSupported()) {
      attachHls();
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      video.addEventListener("loadedmetadata", () => {
        if (!destroyed) {
          muteNativeSubs();
          onStatusRef.current?.("ready");
          startAutoplay();
        }
      });
    } else {
      onStatusRef.current?.("error");
    }

    if (autoFullscreen && rootRef.current) {
      toggleTheaterFullscreen(rootRef.current, { video });
    }

    return () => {
      destroyed = true;
      video.textTracks?.removeEventListener?.("addtrack", muteNativeSubs);
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
    toggleTheaterFullscreen(rootRef.current, { video: videoRef.current });
    bumpOsd();
  }

  const gestureRef = useRef(null);
  const stageRef = useRef({
    onStageActivate,
    onStageDoubleActivate,
    toggleFullscreen,
    applyBottomThird: () => {},
    pausedFrameClean: false,
  });
  useEffect(() => {
    stageRef.current = {
      onStageActivate,
      onStageDoubleActivate,
      toggleFullscreen,
      applyBottomThird,
      pausedFrameClean,
    };
  });

  function pictureOffset(event) {
    const rect = rootRef.current?.getBoundingClientRect();
    const y = (event.clientY ?? event.changedTouches?.[0]?.clientY ?? 0) - (rect?.top || 0);
    return { offsetY: y, height: rect?.height || 0 };
  }

  useEffect(() => {
    const handle = createStageGesture({
      onSingle: (event) => {
        if (isTheaterChromeTarget(event.target)) return;
        if (stageRef.current.pausedFrameClean) {
          bottomTapRef.current = { visibleAtPointerDown: false };
          stageRef.current.applyBottomThird?.();
          return;
        }
        const { offsetY, height } = pictureOffset(event);
        dispatchPictureTap({
          offsetY,
          height,
          togglePlayback: () => {
            const zone = skipZoneFromClientX(
              (event.clientX ?? event.changedTouches?.[0]?.clientX ?? 0) -
                (rootRef.current?.getBoundingClientRect()?.left || 0),
              rootRef.current?.getBoundingClientRect()?.width || 0,
            );
            stageRef.current.onStageActivate?.(event, zone);
          },
          toggleOsd: () => stageRef.current.applyBottomThird?.(),
        });
      },
      onDouble: (event) => {
        if (isTheaterChromeTarget(event.target)) return;
        if (stageRef.current.pausedFrameClean) {
          bottomTapRef.current = { visibleAtPointerDown: false };
          stageRef.current.applyBottomThird?.();
          return;
        }
        const { offsetY, height } = pictureOffset(event);
        if (pictureTapIntent(offsetY, height) === "osd") {
          stageRef.current.applyBottomThird?.();
          return;
        }
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

  function publishPlaying() {
    const video = videoRef.current;
    const held = pictureHoldRef.current;
    if (
      held &&
      !shouldRevealPlaybackPicture({
        holdingSeek: true,
        readyState: video?.readyState ?? 0,
        videoWidth: video?.videoWidth ?? 0,
      })
    ) {
      noteWaiting();
      return;
    }
    if (held) onPictureReadyRef.current?.();
    notePlayingFrame();
    onPlaying?.();
    onStatus?.("playing");
  }

  const frame = playStageChrome(blackFrame);

  return (
    <div
      ref={rootRef}
      className={`theater-player live-player ${frame.className} ${className}`.trim()}
      data-testid={testId}
      data-osd={osdVisible ? "visible" : "hidden"}
      data-picture-hold={pictureHold ? "true" : "false"}
      data-play-frame={frame.dataPlayFrame}
      tabIndex={0}
      onMouseMove={handlePointerMove}
      onFocus={bumpOsd}
      onPointerDown={(event) => {
        if (!isTheaterChromeTarget(event.target)) suppressHoldTextSelection(event);
        const rect = rootRef.current?.getBoundingClientRect();
        const y = (event.clientY ?? 0) - (rect?.top || 0);
        if (pictureTapIntent(y, rect?.height || 0) === "osd") {
          bottomTapRef.current = { visibleAtPointerDown: osdVisible };
          return;
        }
        bottomTapRef.current = null;
        handlePointerMove(event);
        if (!isTheaterChromeTarget(event.target)) startHoldToRate();
      }}
      onPointerUp={(event) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        const endedHold = endHoldToRate();
        if (
          endedHold.held &&
          holdToRateShouldCancelTap({ downAtMs: endedHold.downAt, upAtMs: Date.now() })
        ) {
          gestureRef.current?.cancel?.();
          return;
        }
        gestureRef.current?.(event);
      }}
      onPointerCancel={() => {
        endHoldToRate();
        gestureRef.current?.cancel?.();
      }}
      onPointerLeave={() => {
        if (holdRef.current.active) {
          endHoldToRate();
          gestureRef.current?.cancel?.();
        }
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
        data-picture-hold={pictureHold ? "true" : "false"}
        onTimeUpdate={(event) => onTimeUpdate?.(event.currentTarget)}
        onEnded={() => onEnded?.()}
        onPlaying={publishPlaying}
        onLoadedData={() => {
          if (pictureHoldRef.current) publishPlaying();
        }}
        onResize={() => {
          if (pictureHoldRef.current) publishPlaying();
        }}
        onPause={() => {
          endHoldToRate();
          onStatus?.("paused");
        }}
        onWaiting={() => {
          noteWaiting();
          onWaiting?.();
        }}
        onStalled={() => noteWaiting()}
        onRateChange={syncHoldChip}
      />

      {pictureHold && holdFrame ? (
        <img
          className="theater-seek-hold-frame"
          src={holdFrame}
          alt=""
          aria-hidden="true"
          data-testid={`${testId}-seek-hold`}
        />
      ) : null}

      <TuningInterstitial
        active={showTuning}
        testId={`${testId}-tuning`}
      />

      {healthNode}
      {holdRateOn ? (
        <div className="theater-rate-chip" role="status" data-testid={`${testId}-rate-chip`}>
          2x
        </div>
      ) : null}
      {bufferingEnabled &&
      shouldShowLibraryBufferingChip({
        displayedHealth: bufferUi.displayed,
        hasError: Boolean(error),
        seekFailed: false,
        readyState: videoRef.current?.readyState ?? 0,
        videoWidth: videoRef.current?.videoWidth ?? 0,
        waiting: waitingSinceRef.current != null || pictureHold,
      }) ? (
        <BufferingIndicator
          label={libraryBufferingCopy(bufferUi.displayed)}
          testId={`${testId}-buffering`}
          variant="chip"
        />
      ) : null}
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
export function requestTheaterFullscreen(root, video) {
  toggleTheaterFullscreen(root, { video });
}
