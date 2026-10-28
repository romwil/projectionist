import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import Hls from "hls.js";
import type { ErrorData } from "hls.js";
import { LIVE_STALL_ESCALATE_MS, LIVE_STALL_NOTICE_MS } from "../../lib/liveChannels.js";
import BufferingIndicator from "./BufferingIndicator";
import TuningInterstitial from "./TuningInterstitial";
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

export type TheaterPlaybackStatus = "idle" | "loading" | "ready" | "playing" | "paused" | "error";
export type TheaterMediaMode = "hls" | "progressive";
export type TheaterSkipZone = "left" | "center" | "right";
export type TheaterStreamHealth = "ok" | "buffering" | "stalled";

export type TheaterBufferUi = {
  displayed: TheaterStreamHealth;
  stickyUntil: number | null;
};

export type TheaterAutoplayResult = {
  playing: boolean;
  muted: boolean;
  unmuteOnTap?: boolean;
};

export type TheaterAttachApi = {
  remount: () => void;
};

export type TheaterHlsErrorContext = {
  hls: Hls;
  remount: () => void;
  video: HTMLVideoElement;
};

export type TheaterKeyApi = {
  toggleFullscreen: () => void;
  bumpOsd: () => void;
  video: HTMLVideoElement | null;
};

export type TheaterStagePointerEvent = {
  clientX?: number;
  clientY?: number;
  changedTouches?: ArrayLike<{ clientX: number; clientY: number }>;
  target?: EventTarget | null;
};

export type TheaterPlayerProps = {
  src?: string;
  poster?: string;
  className?: string;
  testId?: string;
  videoTestId?: string;
  osdTestId?: string;
  autoFullscreen?: boolean;
  loading?: boolean;
  loadingCopy?: string;
  /** When true, show CRT static interstitial (Play start / Live tune). */
  tuning?: boolean;
  /**
   * Session-restart seek: hide the video element until the new playlist
   * can paint. `holdFrame` is the previous picture (or empty for the poster).
   */
  pictureHold?: boolean;
  holdFrame?: string;
  onPictureReady?: (...args: any[]) => void;
  error?: string;
  errorNode?: ReactNode;
  healthNode?: ReactNode;
  gestureNode?: ReactNode;
  osd?: ReactNode;
  osdVisible?: boolean;
  onBumpOsd?: (...args: any[]) => void;
  onStatus?: (status: TheaterPlaybackStatus) => void;
  onTimeUpdate?: (video: HTMLVideoElement) => void;
  onEnded?: (...args: any[]) => void;
  onPlaying?: (...args: any[]) => void;
  onWaiting?: (...args: any[]) => void;
  onStalled?: (...args: any[]) => void;
  onStageActivate?: (event: TheaterStagePointerEvent, zone: TheaterSkipZone) => void;
  onStageDoubleActivate?: (event: TheaterStagePointerEvent, zone: TheaterSkipZone) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLDivElement>, api: TheaterKeyApi) => void;
  onVideoRef?: (el: HTMLVideoElement | null) => void;
  onHlsRef?: (hls: Hls | null) => void;
  onRootRef?: (el: HTMLDivElement | null) => void;
  onOsdVisibility?: (visible: boolean) => void;
  pausedFrameClean?: boolean;
  /** After a shrunk-play reload, start muted if unmuted autoplay is blocked. */
  resumeMutedIfBlocked?: boolean;
  onAutoplayResult?: (result: TheaterAutoplayResult) => void;
  /** Library Play only: press-and-hold 2x. Live TV must leave this false. */
  holdToDoubleSpeed?: boolean;
  /** Library Play: hide the blurred poster border and use a black letterbox. */
  blackFrame?: boolean;
  /** Library Play only: delayed buffering OSD. Live has its own chips. */
  bufferingEnabled?: boolean;
  /**
   * Live bumper/filler files use progressive (mp4) attach. Default HLS.
   * Empty `src` skips attach (preroll, resume gate, weather boards).
   */
  mediaMode?: TheaterMediaMode;
  /** Bump to remount HLS against the same URL without re-tuning. */
  attachKey?: number;
  /** Live: tryPlayLiveVideo so Safari/iPad can unmute-fallback. */
  playMedia?: (video: HTMLVideoElement) => Promise<string | undefined>;
  /**
   * Live HLS recovery. Return true to skip the shell’s default fatal handler.
   * `ctx.remount()` re-attaches the current src without a new tune.
   */
  onHlsError?: (data: ErrorData, ctx: TheaterHlsErrorContext) => boolean | void;
  onManifestParsed?: (hls: Hls) => void;
  onSubtitleTracks?: (hls: Hls) => void;
  onAttachApi?: (api: TheaterAttachApi | null) => void;
  /** Extra data-* on the stage root (channel, stream-health, weather sky). */
  dataAttrs?: Record<string, string | number | boolean | undefined> | null;
  children?: ReactNode;
};

type StageGestureHandle = ((event: TheaterStagePointerEvent) => void) & { cancel: () => void };

// JS helpers infer only defaulted destructure keys; keep the runtime call shape.
const createStageGestureTyped = createStageGesture as (opts?: {
  onSingle?: (event: TheaterStagePointerEvent) => void;
  onDouble?: (event: TheaterStagePointerEvent) => void;
  delay?: number;
}) => StageGestureHandle;

const holdToRateShouldCancelTapTyped = holdToRateShouldCancelTap as (opts?: {
  downAtMs?: number;
  upAtMs?: number;
  delayMs?: number;
}) => boolean;

/**
 * Shared theater shell: auth’d HLS video, idle OSD, fullscreen, stall copy.
 * LivePlayer mounts this for tune / Ch± / guide %. LibraryPlayer adds VOD
 * skip / scrub / resume. Weather uses the same stage with no media src.
 */
export default function TheaterPlayer({
  src = "",
  poster = "",
  className = "",
  testId = "theater-player",
  videoTestId = "theater-player-video",
  osdTestId,
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
  onStalled,
  onStageActivate,
  onStageDoubleActivate,
  onKeyDown,
  onVideoRef,
  onHlsRef,
  onRootRef,
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
  /**
   * Live bumper/filler files use progressive (mp4) attach. Default HLS.
   * Empty `src` skips attach (preroll, resume gate, weather boards).
   */
  mediaMode = "hls",
  /** Bump to remount HLS against the same URL without re-tuning. */
  attachKey = 0,
  /** Live: tryPlayLiveVideo so Safari/iPad can unmute-fallback. */
  playMedia,
  /**
   * Live HLS recovery. Return true to skip the shell’s default fatal handler.
   * `ctx.remount()` re-attaches the current src without a new tune.
   */
  onHlsError,
  onManifestParsed,
  onSubtitleTracks,
  onAttachApi,
  /** Extra data-* on the stage root (channel, stream-health, weather sky). */
  dataAttrs = null,
  children,
}: TheaterPlayerProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pointerPosRef = useRef<{ x: number; y: number } | null>(null);
  // Keep parent callbacks out of the HLS effect deps. LibraryPlayer (and Live)
  // pass inline onHlsRef / onStatus — putting those in deps remounts hls.js on
  // every status tick (loading→ready→playing), which looks like: OSD flash,
  // poster still, then permanent stall with no honest error.
  const onStatusRef = useRef(onStatus);
  const onHlsRefRef = useRef(onHlsRef);
  const onVideoRefRef = useRef(onVideoRef);
  const onRootRefRef = useRef(onRootRef);
  const onBumpOsdRef = useRef(onBumpOsd);
  const onOsdVisibilityRef = useRef(onOsdVisibility);
  const onPictureReadyRef = useRef(onPictureReady);
  const pictureHoldRef = useRef(pictureHold);
  const resumeMutedIfBlockedRef = useRef(resumeMutedIfBlocked);
  const onAutoplayResultRef = useRef(onAutoplayResult);
  const holdToDoubleSpeedRef = useRef(holdToDoubleSpeed);
  const bufferingEnabledRef = useRef(bufferingEnabled);
  const playMediaRef = useRef(playMedia);
  const onHlsErrorRef = useRef(onHlsError);
  const onManifestParsedRef = useRef(onManifestParsed);
  const onSubtitleTracksRef = useRef(onSubtitleTracks);
  const onAttachApiRef = useRef(onAttachApi);
  const bottomTapRef = useRef<{ visibleAtPointerDown: boolean } | null>(null);
  const holdRef = useRef({ active: false, downAt: 0 });
  const waitingSinceRef = useRef<number | null>(null);
  const bufferUiRef = useRef<TheaterBufferUi>({ displayed: "ok", stickyUntil: null });
  const bufferTimerRef = useRef<number | null>(null);
  const [holdRateOn, setHoldRateOn] = useState(false);
  const [bufferUi, setBufferUi] = useState<TheaterBufferUi>({ displayed: "ok", stickyUntil: null });
  useEffect(() => {
    onStatusRef.current = onStatus;
    onHlsRefRef.current = onHlsRef;
    onVideoRefRef.current = onVideoRef;
    onRootRefRef.current = onRootRef;
    onBumpOsdRef.current = onBumpOsd;
    onOsdVisibilityRef.current = onOsdVisibility;
    onPictureReadyRef.current = onPictureReady;
    pictureHoldRef.current = pictureHold;
    resumeMutedIfBlockedRef.current = resumeMutedIfBlocked;
    onAutoplayResultRef.current = onAutoplayResult;
    holdToDoubleSpeedRef.current = holdToDoubleSpeed;
    bufferingEnabledRef.current = bufferingEnabled;
    playMediaRef.current = playMedia;
    onHlsErrorRef.current = onHlsError;
    onManifestParsedRef.current = onManifestParsed;
    onSubtitleTracksRef.current = onSubtitleTracks;
    onAttachApiRef.current = onAttachApi;
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
    }) as TheaterStreamHealth;
    const next = stepLibraryBufferingUi(bufferUiRef.current, { rawHealth: raw, nowMs }) as TheaterBufferUi;
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

  useEffect(() => {
    onRootRefRef.current?.(rootRef.current);
    return () => onRootRefRef.current?.(null);
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
      const customPlay = playMediaRef.current;
      if (customPlay) {
        customPlay(video).then((next) => {
          if (destroyed) return;
          onStatusRef.current?.(next === "playing" ? "playing" : (next as TheaterPlaybackStatus) || "paused");
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
      const hls = new Hls(theaterHlsConfig() as ConstructorParameters<typeof Hls>[0]);
      hlsRef.current = hls;
      onHlsRefRef.current?.(hls);
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (destroyed) return;
        muteNativeSubs();
        onStatusRef.current?.("ready");
        onManifestParsedRef.current?.(hls);
        startAutoplay();
      });
      hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, () => {
        muteNativeSubs();
        onSubtitleTracksRef.current?.(hls);
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (destroyed || !data) return;
        const handled = onHlsErrorRef.current?.(data, { hls, remount: attachHls, video });
        if (handled) return;
        if (!data.fatal) return;
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

    const attachProgressive = () => {
      if (destroyed || !video) return;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
        onHlsRefRef.current?.(null);
      }
      const onReady = () => {
        if (destroyed) return;
        muteNativeSubs();
        onStatusRef.current?.("ready");
        startAutoplay();
      };
      video.addEventListener("loadedmetadata", onReady, { once: true });
      video.src = src;
    };

    const remount = () => {
      if (destroyed) return;
      if (mediaMode === "progressive") attachProgressive();
      else attachHls();
    };

    video.textTracks?.addEventListener?.("addtrack", muteNativeSubs);

    if (mediaMode === "progressive") {
      attachProgressive();
    } else if (Hls.isSupported()) {
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

    onAttachApiRef.current?.({ remount });

    if (autoFullscreen && rootRef.current) {
      toggleTheaterFullscreen(rootRef.current, { video: video as any });
    }

    return () => {
      destroyed = true;
      onAttachApiRef.current?.(null);
      video.textTracks?.removeEventListener?.("addtrack", muteNativeSubs);
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
        onHlsRefRef.current?.(null);
      }
      video.removeAttribute("src");
      video.load();
    };
  }, [src, autoFullscreen, attachKey, mediaMode]);

  function toggleFullscreen() {
    toggleTheaterFullscreen(rootRef.current, { video: videoRef.current });
    bumpOsd();
  }

  const gestureRef = useRef<StageGestureHandle | null>(null);
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

  function pictureOffset(event: TheaterStagePointerEvent) {
    const rect = rootRef.current?.getBoundingClientRect();
    const y = (event.clientY ?? event.changedTouches?.[0]?.clientY ?? 0) - (rect?.top || 0);
    return { offsetY: y, height: rect?.height || 0 };
  }

  useEffect(() => {
    const handle = createStageGestureTyped({
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
            ) as TheaterSkipZone;
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
        ) as TheaterSkipZone;
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

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const pos = { x: event.clientX, y: event.clientY };
    const prev = pointerPosRef.current;
    pointerPosRef.current = pos;
    if (!prev || Math.abs(pos.x - prev.x) + Math.abs(pos.y - prev.y) > 4) {
      bumpOsd();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
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
  const extraData: Record<string, string | number | boolean | undefined> = {};
  if (dataAttrs && typeof dataAttrs === "object") {
    for (const [key, value] of Object.entries(dataAttrs)) {
      extraData[key.startsWith("data-") ? key : `data-${key}`] = value;
    }
  }
  const showVideo = Boolean(src) || pictureHold;

  return (
    <div
      ref={rootRef}
      className={`theater-player live-player ${frame.className} ${className}`.trim()}
      data-testid={testId}
      data-osd={osdVisible ? "visible" : "hidden"}
      data-picture-hold={pictureHold ? "true" : "false"}
      data-play-frame={frame.dataPlayFrame}
      data-media={src ? mediaMode : "none"}
      tabIndex={0}
      {...extraData}
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
          holdToRateShouldCancelTapTyped({ downAtMs: endedHold.downAt, upAtMs: Date.now() })
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
        hidden={!showVideo}
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
        onStalled={() => {
          noteWaiting();
          onStalled?.();
        }}
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
        data-testid={osdTestId || `${testId}-osd`}
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
export function requestTheaterFullscreen(root: HTMLElement | null, video?: HTMLVideoElement | null) {
  toggleTheaterFullscreen(root, { video: video as any });
}
