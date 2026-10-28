/** `any` in this file is API/DOM bags until Wave 4 client generics. */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  downloadLiveChannelSubtitles,
  fetchNextPreroll,
  getLiveChannelSubtitles,
  tuneLiveChannel,
} from "../../api/client";
import {
  buildFlexLowerThird,
  buildOsdModel,
  classifyLiveStreamHealth,
  formatClock,
  formatWallTime,
  LIVE_CC_EMPTY_STREAM,
  LIVE_STALL_ESCALATE_MS,
  LIVE_STALL_NOTICE_MS,
  flexPlaybackPlan,
  flexSlateCopy,
  liveHlsErrorPolicy,
  liveStreamUrl,
  mergeLiveCcTracks,
  recordLivePlaybackDiag,
  stepLiveStreamHealthUi,
  summarizeLiveVideoBuffer,
  liveShowsTapHint,
  liveUiStatusFromTheater,
  toggleLiveVideoPlayback,
  tryPlayLiveVideo,
} from "../../lib/liveChannels.js";
import { toggleTheaterFullscreen } from "../../lib/theaterPlayer.js";
import {
  clampSubtitleDelay,
  liveSubtitleLookupSec,
  resolveSubtitlePresentation,
  silenceNativeTextTracks,
  SUBTITLE_NO_TEXT_TRACKS,
} from "../../lib/subtitleCues.js";
import { formatLiveStreamError, liveStreamHealthCopy } from "../../lib/liveChannelsCopy.js";
import { pickLiveSoftStallPhrase } from "../../lib/liveStreamSoftStallCopy.js";
import {
  isPauseBoundaryDismissed,
  pauseBoundaryForPlaybackStatus,
  pauseBoundaryOnPauseGesture,
  programEndSecFromOsd,
  shouldPromptPausePastBoundary,
} from "../../lib/livePauseBoundary.js";
import { livePrerollCueId, normalizePrerollPayload } from "../../lib/prerollClient.js";
import LiveProgramHoverCard from "./LiveProgramHoverCard";
import TheaterPlayer from "../theater/TheaterPlayer";
import PrerollStage from "../theater/PrerollStage";
import SubtitleOverlay from "../theater/SubtitleOverlay";
import SubtitlePicker from "../theater/SubtitlePicker";
import useSubtitleCues from "../theater/useSubtitleCues.js";

/**
 * Fullscreen-capable HLS player with cable-box OSD + subtitle picker.
 */
/** Props for LivePlayer. `any` = live channel/program JSON until Wave 4. */
type LivePlayerProps = {
  channel?: any;
  channels?: any[];
  selectedProgram?: any;
  onChannelChange?: (...args: any[]) => void;
  compact?: boolean;
  autoFullscreen?: boolean;
  className?: string;
};

export default function LivePlayer({
  channel,
  channels = [],
  selectedProgram = null,
  onChannelChange,
  compact = false,
  autoFullscreen = false,
  className = "",
}: LivePlayerProps) {
  const videoRef = useRef<any>(null);
  const nextHoverLeaveTimer = useRef<any>(null);
  const [nextHover, setNextHover] = useState<any>(null);
  const rootRef = useRef<any>(null);
  const hlsRef = useRef<any>(null);
  const statusRef = useRef("idle");
  const [rootEl, setRootEl] = useState<any>(null);
  const [mediaSrc, setMediaSrc] = useState("");
  const [mediaMode, setMediaMode] = useState("hls");
  const [attachKey, setAttachKey] = useState(0);
  const [shellOsd, setShellOsd] = useState(true);
  const networkRetriesRef = useRef(0);
  const recoverTimerRef = useRef<any>(null);
  const stallNudgeTimerRef = useRef<any>(null);
  const waitingSinceRef = useRef<any>(null);
  const mediaStalledRef = useRef(false);
  const hlsBufferStalledRef = useRef(false);
  const healthUiRef = useRef({ displayed: "ok", stickyUntil: null });
  const stallUiTimerRef = useRef<any>(null);
  const lastProgressAtRef = useRef<any>(null);
  const lastProgressTimeRef = useRef<any>(null);
  const lastMediaUrlRef = useRef("");
  const [osdTick, setOsdTick] = useState(Date.now());
  const [status, setStatus] = useState("idle");
  const [scheduleEpoch, setScheduleEpoch] = useState(0);
  const [streamHealth, setStreamHealth] = useState("ok");
  const [softStallPhrase, setSoftStallPhrase] = useState("");
  const [error, setError] = useState("");
  const [textTracks, setTextTracks] = useState<any[]>([]);
  const [activeTrack, setActiveTrack] = useState(-1);
  const [ccOpen, setCcOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const [plexCc, setPlexCc] = useState<any>(null);
  const [ccDownloadBusy, setCcDownloadBusy] = useState(false);
  const [ccDownloadNote, setCcDownloadNote] = useState("");
  const [subDelay, setSubDelay] = useState(0);
  const [preroll, setPreroll] = useState<any>(null); // null = none/ready; object = playing; undefined = resolving
  const [pauseBoundary, setPauseBoundary] = useState<any>(null);
  const [flexSlate, setFlexSlate] = useState("");
  const pauseProgramEndRef = useRef<any>(null);
  const finishThenLiveRef = useRef(false);
  const remountLiveRef = useRef<any>(null);
  const tuneOffsetSecRef = useRef<number | null>(null);
  const lastFilePositionRef = useRef<number | null>(null);

  const channelId = channel?.id || "";
  const osd = buildOsdModel(channel, osdTick, { selectedProgram });
  const liveCue = livePrerollCueId(osd, osdTick);
  const prerollCueRef = useRef("");
  const [prerollEpoch, setPrerollEpoch] = useState(channelId);
  if (prerollEpoch !== channelId) {
    setPrerollEpoch(channelId);
    setPreroll(null);
    setPauseBoundary(null);
    setFlexSlate("");
    prerollCueRef.current = "";
    finishThenLiveRef.current = false;
    pauseProgramEndRef.current = null;
    tuneOffsetSecRef.current = null;
    lastFilePositionRef.current = null;
  }
  const nowPlexKey = osd?.plexRatingKey || channel?.now?.plex_rating_key || "";
  const ccMerged = mergeLiveCcTracks(textTracks, plexCc);
  // Plex tracks (embedded or sidecar) are drawn by Projectionist itself, so they work
  // whether or not the Live encode carries captions.
  const activePlexTrack = ccMerged.plexTracks.find((track) => (track as any).index === activeTrack) || null;
  const plexSubs = useSubtitleCues(activePlexTrack?.proxyUrl || "");
  const nativeTrackIndex =
    typeof activeTrack === "number" && activeTrack >= 0 && !activePlexTrack ? activeTrack : -1;
  const subPresentation = resolveSubtitlePresentation({
    softTrackSelected: Boolean(activePlexTrack),
    softTrackReady: plexSubs.state === "ready",
    nativeTrackIndex,
  });
  const getSubtitleTimeSec = useCallback(() => {
    const video = videoRef.current;
    if (!video) return Number.NaN;
    const lookup = liveSubtitleLookupSec({
      currentTimeSec: video.currentTime,
      programElapsedSec: tuneOffsetSecRef.current,
    });
    if (Number.isFinite(lookup)) lastFilePositionRef.current = lookup;
    return lookup;
  }, []);

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

  function clearStallUiTimer() {
    if (stallUiTimerRef.current) {
      clearTimeout(stallUiTimerRef.current);
      stallUiTimerRef.current = null;
    }
  }

  function resetStallUiState() {
    clearStallUiTimer();
    healthUiRef.current = { displayed: "ok", stickyUntil: null };
    waitingSinceRef.current = null;
    mediaStalledRef.current = false;
    hlsBufferStalledRef.current = false;
    setStreamHealth("ok");
    setSoftStallPhrase("");
  }

  /**
   * Recompute raw stall signals → notice-delayed + sticky displayed health.
   * Returns displayed health; bumps OSD only when a chip newly appears (or escalates).
   */
  function recomputeStreamHealth(nowMs = Date.now(), { bump = false } = {}) {
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
    const raw = classifyLiveStreamHealth({
      playbackStatus: statusRef.current,
      waiting,
      mediaStalled: mediaStalledRef.current,
      hlsBufferStalled: hlsBufferStalledRef.current,
      playheadFrozen,
      waitingMs,
    });
    const prevDisplayed = healthUiRef.current.displayed;
    const nextUi = stepLiveStreamHealthUi((healthUiRef as any).current, { rawHealth: raw, nowMs });
    (healthUiRef as any).current = nextUi;
    const next = nextUi.displayed;
    setStreamHealth((prev) => (prev === next ? prev : next));
    if (next === "ok") {
      setSoftStallPhrase("");
    } else {
      // Lock one wry line for this soft-stall episode (no flicker on recompute).
      setSoftStallPhrase((phrase) => phrase || pickLiveSoftStallPhrase({ exclude: phrase }));
    }
    if (
      bump
      && next !== "ok"
      && (prevDisplayed === "ok" || (prevDisplayed === "buffering" && next === "stalled"))
    ) {
      bumpOsd();
    }
    // Arm timers so notice/hold edges fire without waiting for the 1s poll.
    armStallUiTimer(nowMs);
    return next;
  }

  function armStallUiTimer(nowMs = Date.now()) {
    if (stallUiTimerRef.current) return;
    const waitingSince = waitingSinceRef.current;
    const stickyUntil = healthUiRef.current.stickyUntil;
    let delay = null;
    if (waitingSince != null && healthUiRef.current.displayed === "ok") {
      delay = Math.max(0, LIVE_STALL_NOTICE_MS - (nowMs - waitingSince));
    } else if (stickyUntil != null && healthUiRef.current.displayed !== "ok") {
      delay = Math.max(0, stickyUntil - nowMs);
    }
    if (delay == null) return;
    stallUiTimerRef.current = setTimeout(() => {
      stallUiTimerRef.current = null;
      recomputeStreamHealth(Date.now(), { bump: true });
    }, delay);
  }

  function noteStallSignal() {
    if (waitingSinceRef.current == null) waitingSinceRef.current = Date.now();
    return recomputeStreamHealth(Date.now(), { bump: true });
  }

  function clearStallSignals({ logEvent }: any = {}) {
    const had =
      waitingSinceRef.current != null
      || mediaStalledRef.current
      || hlsBufferStalledRef.current
      || healthUiRef.current.displayed !== "ok"
      || streamHealth !== "ok";
    clearStallUiTimer();
    waitingSinceRef.current = null;
    mediaStalledRef.current = false;
    hlsBufferStalledRef.current = false;
    // Route recovery through hysteresis — do not hard-clear the chip/chrome.
    recomputeStreamHealth(Date.now(), { bump: false });
    if (had && logEvent) {
      recordLivePlaybackDiag(logEvent, diagBase());
    }
  }

  function bumpOsd() {
    setShellOsd(true);
  }

  useEffect(() => {
    const timer = setInterval(() => setOsdTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!rootEl || typeof ResizeObserver === "undefined") return undefined;
    let debounce: any = null;
    const ro = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width || 0;
      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(() => setNarrow(width < 480), 100);
    });
    ro.observe(rootEl);
    return () => {
      ro.disconnect();
      if (debounce) clearTimeout(debounce);
    };
  }, [rootEl]);

  // A Plex track belongs to one airing — drop it when the title behind the channel changes.
  useEffect(() => {
    setActiveTrack((current) => (typeof current === "string" ? -1 : current));
    setSubDelay(0);
  }, [channelId, nowPlexKey]);

  // Same caption path as library Play: our VTT proxy, fetch text CC when needed.
  useEffect(() => {
    if (!channelId) {
      setPlexCc(null);
      setCcDownloadNote("");
      return undefined;
    }
    let cancelled = false;
    setCcDownloadNote("");
    (async () => {
      try {
        const listed = await getLiveChannelSubtitles(channelId);
        if (cancelled) return;
        const first = mergeLiveCcTracks([], listed);
        let downloaded = null;
        if (first.needsFetch && listed?.can_download) {
          setCcDownloadNote("Looking for text captions…");
          try {
            const result = await downloadLiveChannelSubtitles(channelId);
            if (cancelled) return;
            downloaded = Array.isArray(result?.streams) ? result.streams : [];
            if (result?.ok && !downloaded.length) {
              const refreshed = await getLiveChannelSubtitles(channelId);
              if (cancelled) return;
              downloaded = refreshed?.plex_streams ?? [];
            }
          } catch {
            // Keep listed tracks — empty is better than wiping a usable sidecar.
          }
        }
        if (cancelled) return;
        const payload = { ...(listed || {}), downloaded_streams: downloaded };
        setPlexCc(payload);
        const resolved = mergeLiveCcTracks([], payload);
        if (resolved.autoSelectIndex !== -1) setActiveTrack(resolved.autoSelectIndex);
        if (resolved.plexTracks.length) {
          setCcDownloadNote("");
        } else if (first.needsFetch) {
          setCcDownloadNote(String(listed?.empty_message || SUBTITLE_NO_TEXT_TRACKS));
        } else {
          setCcDownloadNote("");
        }
      } catch {
        if (!cancelled) {
          setPlexCc(null);
          setCcDownloadNote("");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [channelId, nowPlexKey]);

  useEffect(() => {
    if (plexSubs.state !== "error" || !activePlexTrack) return;
    setActiveTrack(-1);
    setCcDownloadNote(SUBTITLE_NO_TEXT_TRACKS);
  }, [plexSubs.state, activePlexTrack]);

  // Requests a bumper only when a movie is starting or about to air.
  useEffect(() => {
    if (!channelId || !liveCue) return undefined;
    const token = `${channelId}:${liveCue}`;
    if (prerollCueRef.current === token) return undefined;
    prerollCueRef.current = token;
    let cancelled = false;
    (async () => {
      try {
        const bumper = normalizePrerollPayload(await fetchNextPreroll("live"));
        if (!cancelled) setPreroll(bumper);
      } catch {
        if (!cancelled) setPreroll(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [channelId, liveCue]);

  // While paused, ask when wall-clock crosses the program that was airing.
  useEffect(() => {
    if (status !== "paused") return undefined;
    if (pauseProgramEndRef.current == null) {
      pauseProgramEndRef.current = programEndSecFromOsd(osd);
    }
    const tick = () => {
      if (
        shouldPromptPausePastBoundary({
          paused: true,
          programEndsAtSec: pauseProgramEndRef.current,
          nowSec: Date.now() / 1000,
          dismissed: isPauseBoundaryDismissed(pauseBoundary),
        })
      ) {
        setPauseBoundary((prev: any) => (prev?.open ? prev : { open: true }));
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [status, osdTick, pauseBoundary, osd]);

  // Rejoin/Finish sets `{ open: false }` so this pause does not immediately
  // re-prompt. Resume bypasses togglePlayback, which used to leave that
  // dismissal stuck. Drop it once playback leaves pause.
  useEffect(() => {
    if (status === "paused") return;
    setPauseBoundary((prev: any) => {
      const next = pauseBoundaryForPlaybackStatus(prev, status);
      return next === prev ? prev : next;
    });
  }, [status]);

  function syncTracks() {
    const video = videoRef.current;
    if (!video) return;
    const list = [];
    for (let i = 0; i < video.textTracks.length; i += 1) {
      const track = video.textTracks[i];
      list.push({
        index: i,
        label: track.label || track.language || `Track ${i + 1}`,
        language: track.language || "",
      });
    }
    setTextTracks(list);
  }

  function handleSubtitleTracks(hls: any) {
    const subs = hls?.subtitleTracks || [];
    if (subs.length) {
      setTextTracks(
        subs.map((track: any, index: any) => ({
          index,
          label: track.name || track.lang || `CC ${index + 1}`,
          language: track.lang || "",
          viaHls: true,
        })),
      );
    } else {
      syncTracks();
    }
  }

  function handleHlsError(data: any, { hls, remount }: any = {}) {
    const policy = liveHlsErrorPolicy(data, { networkRetries: networkRetriesRef.current });
    const detail = data?.details || "";
    const fatal = Boolean(data?.fatal);
    recordLivePlaybackDiag(fatal ? "hls-error-fatal" : "hls-error", diagBase({
      hlsType: data?.type,
      hlsDetails: detail,
      fatal,
      httpCode: data?.response?.code,
      fragUrl: data?.frag?.url || data?.url || "",
    }));
    networkRetriesRef.current = policy.networkRetries;
    if (policy.stall) {
      hlsBufferStalledRef.current = true;
      noteStallSignal();
    }
    if (policy.keepPlaying) {
      setStatus("playing");
      setError("");
    }
    if (policy.action === "stall-nudge") {
      if (!stallNudgeTimerRef.current) {
        stallNudgeTimerRef.current = setTimeout(() => {
          stallNudgeTimerRef.current = null;
          try {
            hlsRef.current?.startLoad?.();
            recordLivePlaybackDiag("stall-nudge-startLoad", diagBase());
          } catch {
            // ignore
          }
        }, LIVE_STALL_ESCALATE_MS);
      }
      return true;
    }
    if (policy.action === "startLoad") {
      hls?.startLoad?.();
      return true;
    }
    if (policy.action === "remount") {
      if (recoverTimerRef.current) clearTimeout(recoverTimerRef.current);
      recoverTimerRef.current = setTimeout(() => {
        recoverTimerRef.current = null;
        remount?.();
      }, policy.remountDelayMs);
      return true;
    }
    if (policy.action === "recoverMedia") {
      hls?.recoverMediaError?.();
      return true;
    }
    if (policy.action === "fatal") {
      setStatus("error");
      resetStallUiState();
      setError(formatLiveStreamError(data));
      return true;
    }
    return true;
  }

  function handleManifestParsed() {
    setError("");
    recordLivePlaybackDiag("manifest-parsed", diagBase());
    syncTracks();
  }

  function handlePlayerStatus(next: any) {
    if (next === "ready") setError("");
    if (next === "playing") {
      clearStallSignals({ logEvent: "video-playing" });
      lastProgressAtRef.current = Date.now();
      lastProgressTimeRef.current = videoRef.current?.currentTime;
    }
    if (next === "error") {
      setError((prev) => prev || "HLS playback is not supported in this browser.");
    }
    const mapped = liveUiStatusFromTheater(statusRef.current, next);
    statusRef.current = mapped;
    setStatus(mapped);
  }

  function handleWaiting() {
    if (statusRef.current === "loading" || statusRef.current === "paused") return;
    recordLivePlaybackDiag("video-waiting", diagBase());
    noteStallSignal();
  }

  function handleStalled() {
    if (statusRef.current === "loading" || statusRef.current === "paused") return;
    mediaStalledRef.current = true;
    recordLivePlaybackDiag("video-stalled", diagBase());
    noteStallSignal();
  }

  function handleTimeUpdate(video: any) {
    const t = video?.currentTime;
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
  }

  function handleEnded() {
    if (finishThenLiveRef.current) {
      finishThenLiveRef.current = false;
      setPauseBoundary(null);
      pauseProgramEndRef.current = null;
      remountLiveRef.current?.();
    }
    setScheduleEpoch((epoch) => epoch + 1);
  }

  const handleVideoRef = useCallback((el: any) => {
    videoRef.current = el;
  }, []);
  const handleHlsRef = useCallback((hls: any) => {
    hlsRef.current = hls;
  }, []);
  const handleRootRef = useCallback((el: any) => {
    rootRef.current = el;
    setRootEl(el);
  }, []);
  const handleAttachApi = useCallback((api: any) => {
    remountLiveRef.current = api?.remount
      ? () => {
          finishThenLiveRef.current = false;
          api.remount();
        }
      : null;
  }, []);

  useEffect(() => {
    if (!channelId || preroll) {
      setMediaSrc("");
      return undefined;
    }

    let url = liveStreamUrl(channelId);
    lastMediaUrlRef.current = url;
    setError("");
    setStatus("loading");
    resetStallUiState();
    networkRetriesRef.current = 0;
    lastProgressAtRef.current = null;
    lastProgressTimeRef.current = null;
    setTextTracks([]);
    setActiveTrack(-1);
    recordLivePlaybackDiag("tune-start", {
      channelId,
      mediaUrl: url,
    });

    let destroyed = false;
    let holdTimer: any = null;

    // Warm + start-over BEFORE the shell loadSource so tune cannot reset the
    // HLS session out from under the first playlist/segment fetches. Mid-play
    // recoveries remount HLS on the same URL (see liveHlsErrorPolicy).
    (async () => {
      let plan = flexPlaybackPlan(null);
      try {
        const tuned = await tuneLiveChannel(channelId);
        if (destroyed) return;
        const rawOffset = Number(tuned?.offset_ms);
        tuneOffsetSecRef.current =
          Number.isFinite(rawOffset) && rawOffset >= 0 ? rawOffset / 1000 : null;
        plan = flexPlaybackPlan(tuned);
        setFlexSlate(plan.slate ? plan.slateCopy || flexSlateCopy({ nextTitle: osd?.nextDisplay || osd?.nextTitle || tuned?.next_title }) : "");
        if (plan.url) {
          url = plan.url;
          lastMediaUrlRef.current = url;
        }
      } catch (err) {
        recordLivePlaybackDiag("tune-failed", {
          channelId,
          mediaUrl: url,
          message: String((err as any)?.message || err || "tune failed"),
        });
        // Best-effort — player still attempts the stream; errors surface via hls.js.
      }
      if (destroyed) return;
      if (plan.holdMs > 0) {
        holdTimer = window.setTimeout(() => {
          if (!destroyed) setScheduleEpoch((epoch) => epoch + 1);
        }, plan.holdMs);
      }
      // Flex with a filler URL plays in the shared shell. Returning early used
      // to leave an empty <video> covering the stage while Up next kept moving.
      if (plan.play) {
        setMediaMode(plan.progressive ? "progressive" : "hls");
        setMediaSrc(url);
        return;
      }
      setMediaSrc("");
      if (plan.holdMs > 0) {
        setStatus("playing");
        return;
      }
      setMediaMode("hls");
      setMediaSrc(url);
    })();

    return () => {
      destroyed = true;
      if (holdTimer) window.clearTimeout(holdTimer);
      if (recoverTimerRef.current) {
        clearTimeout(recoverTimerRef.current);
        recoverTimerRef.current = null;
      }
      if (stallNudgeTimerRef.current) {
        clearTimeout(stallNudgeTimerRef.current);
        stallNudgeTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tune per channel / bumper / flex hold
  }, [channelId, preroll, scheduleEpoch]);

  useEffect(() => {
    if (!channelId) return undefined;
    const tick = setInterval(() => {
      recomputeStreamHealth(Date.now(), { bump: true });
    }, 1000);
    return () => clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- poll per channel tune
  }, [channelId]);

  useEffect(() => {
    if (!attachKey) return;
    const last = lastFilePositionRef.current;
    if (Number.isFinite(last) && (last as number) >= 0) {
      tuneOffsetSecRef.current = last as number;
    }
  }, [attachKey]);

  useEffect(() => {
    const video = videoRef.current;
    const hls = hlsRef.current;
    if (!video) return;
    // Soft Plex overlay owns presentation — never leave HLS/browser cues showing too.
    if (subPresentation.disableAllNative) {
      if (hls && typeof hls.subtitleTrack === "number") hls.subtitleTrack = -1;
      silenceNativeTextTracks(video);
      return;
    }
    if (hls && typeof hls.subtitleTrack === "number") {
      hls.subtitleTrack = subPresentation.enableNativeTrack ? nativeTrackIndex : -1;
    }
    for (let i = 0; i < video.textTracks.length; i += 1) {
      const track = video.textTracks[i];
      track.mode =
        subPresentation.enableNativeTrack && i === nativeTrackIndex ? "showing" : "disabled";
    }
  }, [
    activeTrack,
    nativeTrackIndex,
    subPresentation.disableAllNative,
    subPresentation.enableNativeTrack,
  ]);

  function selectCcTrack(track: any) {
    if (!track || track.index === -1) {
      setActiveTrack(-1);
      setCcDownloadNote("");
      bumpOsd();
      return;
    }
    if (track.viaPlex && !track.proxyUrl) {
      setActiveTrack(-1);
      setCcDownloadNote(track.unavailableReason || "This track can’t be drawn as text here.");
      bumpOsd();
      return;
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
      setCcDownloadNote((error as any)?.message || "Couldn’t ask Plex for subtitles.");
    } finally {
      setCcDownloadBusy(false);
      bumpOsd();
    }
  }

  function stepChannel(delta: any) {
    if (!onChannelChange || !channels.length) return;
    const idx = channels.findIndex((c) => c.id === channelId);
    const next = Math.max(0, Math.min(channels.length - 1, (idx < 0 ? 0 : idx) + delta));
    const target = channels[next];
    if (target?.id && target.id !== channelId) onChannelChange(target.id);
    bumpOsd();
  }

  function toggleFullscreen() {
    toggleTheaterFullscreen(rootRef.current, { video: videoRef.current });
    bumpOsd();
  }

  async function togglePlayback() {
    const video = videoRef.current;
    if (!video || status === "loading" || status === "error" || pauseBoundary?.open) return;
    bumpOsd();
    const wasPaused = video.paused;
    if (wasPaused) {
      // Resume segment fetching after a live pause.
      hlsRef.current?.startLoad?.();
      clearStallSignals();
      pauseProgramEndRef.current = null;
      setPauseBoundary(null);
    }
    const next = await toggleLiveVideoPlayback(video);
    if (next === "paused") {
      hlsRef.current?.stopLoad?.();
      clearStallSignals();
      pauseProgramEndRef.current = programEndSecFromOsd(osd);
      setPauseBoundary((prev: any) => {
        const nextBoundary = pauseBoundaryOnPauseGesture(prev);
        return nextBoundary === prev ? prev : nextBoundary;
      });
    }
    setStatus(next);
  }

  function rejoinLiveNow() {
    // Suppress only for the rest of this pause. Cleared when playback resumes
    // and again at the start of the next pause gesture.
    setPauseBoundary({ open: false });
    pauseProgramEndRef.current = null;
    finishThenLiveRef.current = false;
    if (remountLiveRef.current) remountLiveRef.current();
    else setAttachKey((key) => key + 1);
    const video = videoRef.current;
    if (video) {
      hlsRef.current?.startLoad?.();
      tryPlayLiveVideo(video).then((next) => setStatus(next));
    }
  }

  function finishThenRejoinLive() {
    finishThenLiveRef.current = true;
    // Same dismissal window as Rejoin: stay shut inside this boundary, then
    // allow a later pause to prompt again.
    setPauseBoundary({ open: false });
    const video = videoRef.current;
    if (video) {
      hlsRef.current?.startLoad?.();
      tryPlayLiveVideo(video).then((next) => setStatus(next));
    }
  }

  function onKeyDown(event: any) {
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
    } else if (key === "Escape") {
      setCcOpen(false);
      bumpOsd();
    }
  }

  const isCompact = compact || narrow;
  const healthCopy = liveStreamHealthCopy(streamHealth, {
    phrase: softStallPhrase,
    allowPick: false,
  });
  const forceOsd = ccOpen || status === "loading" || status === "error" || streamHealth !== "ok";
  const showOsd = forceOsd || shellOsd;
  const flexL3 = buildFlexLowerThird(osd);
  const showTapHint = liveShowsTapHint(status);
  const showHealthChip =
    Boolean(healthCopy) && status !== "loading" && status !== "error" && !error;

  const liveOsd = (
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
          {osd?.poolNotice ? (
            <p className="live-osd-pool-notice" data-testid="live-osd-pool-notice">
              {osd.poolNotice}
            </p>
          ) : null}
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
              anchor: { top: rect.top, bottom: rect.bottom, left: rect.left },
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
        <SubtitlePicker
          testId="live-cc-picker"
          tracks={ccMerged.plexTracks}
          activeId={activeTrack}
          onSelect={selectCcTrack}
          state={activePlexTrack && plexSubs.state !== "error" ? plexSubs.state : "idle"}
          error=""
          note={ccDownloadNote}
          emptyMessage={ccMerged.hasAny ? "" : ccMerged.emptyMessage || LIVE_CC_EMPTY_STREAM}
          delaySec={subDelay}
          onDelayChange={(value) => setSubDelay(clampSubtitleDelay(value))}
          leading={ccMerged.streamTracks.map((track) => (
            <button
              key={`stream-${track.index}`}
              type="button"
              className={`ghost live-cc-option${activeTrack === track.index ? " is-active" : ""}`}
              onClick={() => selectCcTrack(track)}
            >
              {track.label}
            </button>
          ))}
          trailing={
            ccMerged.canDownload ? (
              <button
                type="button"
                className="ghost live-cc-option"
                data-testid="live-cc-ask-plex"
                disabled={ccDownloadBusy}
                onClick={askPlexForSubtitles}
              >
                {ccDownloadBusy ? "Asking Plex…" : "Ask Plex for subtitles"}
              </button>
            ) : null
          }
        />
      ) : null}
    </div>
  );

  return (
    <TheaterPlayer
      src={preroll ? "" : mediaSrc}
      className={`live-player--shell${isCompact ? " live-player--compact" : ""} ${className}`.trim()}
      testId="live-player"
      videoTestId="live-player-video"
      osdTestId="live-osd"
      autoFullscreen={autoFullscreen}
      loading={!preroll && status === "loading"}
      loadingCopy="Tuning…"
      error={error}
      osd={liveOsd}
      osdVisible={forceOsd ? true : undefined}
      onOsdVisibility={setShellOsd}
      onStatus={handlePlayerStatus}
      onVideoRef={handleVideoRef}
      onHlsRef={handleHlsRef}
      onRootRef={handleRootRef}
      onAttachApi={handleAttachApi}
      onHlsError={handleHlsError}
      onManifestParsed={handleManifestParsed}
      onSubtitleTracks={handleSubtitleTracks}
      playMedia={tryPlayLiveVideo}
      mediaMode={mediaMode as any}
      attachKey={attachKey}
      onWaiting={handleWaiting}
      onStalled={handleStalled}
      onTimeUpdate={handleTimeUpdate}
      onEnded={handleEnded}
      onStageActivate={() => {
        togglePlayback();
      }}
      onKeyDown={onKeyDown}
      dataAttrs={{
        channel: channelId,
        status,
        "stream-health": streamHealth,
      }}
      healthNode={
        showHealthChip ? (
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
        ) : null
      }
      gestureNode={
        showTapHint ? (
          <div
            className="live-player-status live-player-status--gesture"
            data-testid="live-player-tap"
          >
            <p>{status === "paused" ? "Paused · tap to play" : "Tap to play"}</p>
          </div>
        ) : null
      }
    >
      {subPresentation.showOverlay ? (
        <SubtitleOverlay
          cues={plexSubs.cues as any}
          getTimeSec={getSubtitleTimeSec}
          delaySec={subDelay}
          testId="live-subtitle-overlay"
        />
      ) : null}

      {preroll ? (
        <PrerollStage
          src={preroll.url}
          onDone={() => setPreroll(null)}
          testId="live-preroll"
        />
      ) : null}

      {!preroll && flexSlate ? (
        <div className="live-flex-slate" data-testid="live-flex-slate">
          <p className="live-flex-slate-kicker">{osd?.name || "Station"}</p>
          <h2 className="live-flex-slate-title">{flexSlate}</h2>
        </div>
      ) : null}

      {pauseBoundary?.open ? (
        <div className="live-pause-boundary" data-testid="live-pause-boundary" role="dialog" aria-modal="true">
          <div className="live-pause-boundary-card">
            <p className="live-pause-boundary-kicker">Program ended while you were paused</p>
            <h2 className="live-pause-boundary-title">What now?</h2>
            <p className="live-pause-boundary-copy muted">
              Finishing a paused file stretches the linear clock for this station —
              other stations stay on the guide. Rejoin live jumps to what&apos;s on now.
            </p>
            <div className="live-pause-boundary-actions">
              <button type="button" className="primary" data-testid="live-rejoin-live" onClick={rejoinLiveNow}>
                Rejoin live
              </button>
              <button type="button" className="ghost" data-testid="live-finish-then-live" onClick={finishThenRejoinLive}>
                Finish this, then rejoin live
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Flex strip mounts on isFlex alone — never nested under showOsd / osdVisible. */}
      {flexL3 ? (
        <aside
          className={`live-flex-l3${showOsd ? " is-osd-up" : ""}`}
          data-testid="live-flex-lower-third"
          data-osd-up={showOsd ? "1" : "0"}
          aria-live="polite"
        >
          <div className="live-flex-l3-inner">
            <div className="live-flex-l3-copy">
              <p className="live-flex-l3-eyebrow" data-testid="live-flex-l3-eyebrow">
                {flexL3.eyebrow}
              </p>
              {flexL3.title ? (
                <p className="live-flex-l3-title" data-testid="live-flex-l3-title">
                  {flexL3.title}
                </p>
              ) : null}
            </div>
            {flexL3.time ? (
              <p className="live-flex-l3-countdown" data-testid="live-flex-l3-time">
                at {flexL3.time}
              </p>
            ) : null}
          </div>
        </aside>
      ) : null}

      <LiveProgramHoverCard
        program={nextHover?.program}
        kind="next"
        open={Boolean(nextHover)}
        anchor={nextHover?.anchor}
        onKeepAlive={() => {
          if (nextHoverLeaveTimer.current) {
            clearTimeout(nextHoverLeaveTimer.current);
            nextHoverLeaveTimer.current = null;
          }
        }}
        onClose={() => setNextHover(null)}
      />
    </TheaterPlayer>
  );
}
