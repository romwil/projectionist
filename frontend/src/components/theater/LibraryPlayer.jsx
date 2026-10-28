import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  downloadLibraryItemSubtitles,
  fetchNextPreroll,
  getLibraryItemSubtitles,
  progressLibraryPlayback,
  seekLibraryPlayback,
  setLibraryPlaybackSubtitles,
  startLibraryPlayback,
  stopLibraryPlayback,
} from "../../api/client";
import { isCompactPlayViewport, isPhonePlayViewport } from "../../lib/chatLayout.js";
import { rememberContinueWatchingProgress } from "../../lib/exploreHubCache.js";
import {
  playerBarActions,
  shrinkOntoPage,
} from "../../lib/inAppPip.js";
import {
  SEEK_FAILED_MESSAGE,
  SEEK_PICTURE_TIMEOUT_MS,
  SEEK_RESTART_DEBOUNCE_MS,
  SKIP_SECONDS,
  bufferedRanges,
  capturePlaybackHoldFrame,
  createScrubCommit,
  longSkipFits,
  canLocalSeekTo,
  canResumeAttachedStream,
  clampTime,
  formatClockMs,
  isDocumentFullscreen,
  libraryWatchPopoutPath,
  nextEpisodeEndCardAction,
  playbackSrcForSeek,
  playheadMsFromMedia,
  runEndCardBackToExplore,
  runNextEpisodeEndCard,
  msFromScrubPct,
  notePlayingBeforeHide,
  scrubPctFromMs,
  seekTimelineOriginMs,
  shouldAutoResumePlayback,
  shouldPauseOnVisibilityHide,
  shouldResumeOnPageShow,
  shouldResumeFromOffset,
  shouldStopSessionOnPageHide,
  shouldSendProgress,
  skipDeltaForZone,
  centerPlayHoldAfterOsdHide,
  playerClosePlacement,
  dispatchLibraryPlayKey,
  isPlayShortcutBlockedTarget,
  theaterKeyAction,
  toggleTheaterFullscreen,
} from "../../lib/theaterPlayer.js";
import {
  UI_PREFS_CHANGED_EVENT,
  loadPauseWhenBackgrounded,
  loadPlayBlackFrame,
  persistPlayBlackFrame,
} from "../../lib/uiPrefs.js";
import {
  SUBTITLE_EMPTY_TRACKS,
  SUBTITLE_NO_TEXT_TRACKS,
  resolvePlaySubtitleTracks,
  resolveSubtitlePresentation,
  silenceNativeTextTracks,
} from "../../lib/subtitleCues.js";
import SubtitleOverlay from "./SubtitleOverlay.jsx";
import useSubtitleCues from "./useSubtitleCues.js";
import { normalizePrerollPayload, shouldPlayMoviePreroll } from "../../lib/prerollClient.js";
import TheaterPlayer from "./TheaterPlayer.jsx";
import LibraryPlayerOsd from "./LibraryPlayerOsd.jsx";
import PrerollStage from "./PrerollStage.jsx";

function displayHeadline(session) {
  if (!session) return "Play";
  if (session.show_title) return session.show_title;
  return session.title || "Play";
}

function displayMeta(session) {
  if (!session) return "";
  if (session.show_title && session.season != null && session.episode != null) {
    return `S${session.season}E${session.episode} · ${session.title || ""}`.replace(/\s·\s$/, "");
  }
  return "";
}

function displayTitle(session) {
  const meta = displayMeta(session);
  if (meta) return `${displayHeadline(session)} · ${meta}`;
  return displayHeadline(session);
}

/** Push a play this screen just recorded onto the Explore Continue Watching rail. */
function rememberPlayedProgress(session, timeMs, durationMs) {
  const ratingKey = String(session?.rating_key || "");
  if (!ratingKey) return;
  const offset = Math.max(0, Math.floor(Number(timeMs) || 0));
  const duration = Math.max(0, Math.floor(Number(durationMs) || 0));
  const finished = duration >= 30_000 && offset >= duration * 0.9;
  rememberContinueWatchingProgress({
    ratingKey,
    showRatingKey: session.show_rating_key || "",
    viewOffsetMs: finished ? 0 : offset,
    durationMs: duration,
    finished: finished || offset <= 0,
    title: session.show_title || session.title || "",
    episodeTitle: session.media_type === "episode" ? session.title || "" : "",
    mediaType: session.media_type || "",
    season: session.season,
    episode: session.episode,
    posterUrl: session.poster_url || "",
    year: session.year,
  });
}

export default function LibraryPlayer({
  ratingKey,
  popout = false,
  floated = false,
  className = "",
  onShrink,
  onAfterPopout,
  /** Set only when a reload restored a shrunk session. Null during a live shrink. */
  continueAtMs = null,
  onPlayhead,
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const autoplayNextRef = useRef(false);
  autoplayNextRef.current = Boolean(location.state?.autoplayNext);
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const sessionRef = useRef(null);
  const lastProgressAtRef = useRef(null);
  const startingRef = useRef(false);
  const wasPlayingBeforeHideRef = useRef(false);
  const pauseWhenBackgroundedRef = useRef(loadPauseWhenBackgrounded());
  /** True while the user is dragging the scrubber — blocks timeupdate from stealing the thumb. */
  const scrubbingRef = useRef(false);
  /** Collapses a slider burst into one seek. iPad Safari must not restart HLS per input. */
  const scrubCommitRef = useRef(null);
  const commitScrubRef = useRef(() => {});
  /** Collapses rapid scrub-end session restarts into one seek. */
  const seekRestartTimerRef = useRef(null);
  const seekRestartPendingMsRef = useRef(null);
  const seekPaintTimerRef = useRef(null);
  const pictureHoldRef = useRef(false);
  const seekReloadArmedRef = useRef(false);
  const seekRestoreMsRef = useRef(null);
  const seekRestoreAttemptedRef = useRef(false);
  const seekFailedRef = useRef(false);
  const seekFailingRef = useRef(false);
  const seekCommittedMsRef = useRef(null);
  const seekTimelineOriginRef = useRef(0);
  const savedMutedRef = useRef(false);
  const wasPlayingRef = useRef(true);
  const failSeekRef = useRef(async () => {});
  const floatedRef = useRef(floated);
  const onPlayheadRef = useRef(onPlayhead);
  const continueAtMsRef = useRef(continueAtMs);
  const pendingUnmuteRef = useRef(false);
  useEffect(() => {
    floatedRef.current = floated;
    onPlayheadRef.current = onPlayhead;
    continueAtMsRef.current = continueAtMs;
  });
  /** Latest skip/toggle so the window key listener does not close over a stale render. */
  const playKeyRef = useRef({ skipBy: () => {}, togglePlayback: () => {} });
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [resumeOpen, setResumeOpen] = useState(false);
  const [ended, setEnded] = useState(false);
  const [endNote, setEndNote] = useState("");
  const [playerKey, setPlayerKey] = useState(() => String(ratingKey || "").trim());
  const [skipChip, setSkipChip] = useState("");
  const [ccOpen, setCcOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [blackFrame, setBlackFrame] = useState(() => loadPlayBlackFrame());
  const [nowMs, setNowMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  /** Non-null while dragging/keyboard-scrubbing — drives the range value instead of playhead. */
  const [scrubPct, setScrubPct] = useState(null);
  const [bufferedEndS, setBufferedEndS] = useState(0);
  const [phone, setPhone] = useState(() => isPhonePlayViewport());
  const [compact, setCompact] = useState(() => isCompactPlayViewport());
  const [longSkip, setLongSkip] = useState(() =>
    longSkipFits({
      width: typeof window !== "undefined" ? window.innerWidth : 0,
      height: typeof window !== "undefined" ? window.innerHeight : 0,
    }),
  );
  const [pipSupported, setPipSupported] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  /** True while scrub/skip is waiting on a Plex session restart. */
  const [seeking, setSeeking] = useState(false);
  /** Bumps when a seek must reload the same playlist URL. */
  const [seekEpoch, setSeekEpoch] = useState(0);
  /** Hide the video element until the restarted playlist can paint. */
  const [pictureHold, setPictureHold] = useState(false);
  const [holdFrame, setHoldFrame] = useState("");
  /** Client-local movie bumper before the feature. */
  const [centerPlayOn, setCenterPlayOn] = useState(true);
  const [osdOpen, setOsdOpen] = useState(true);
  const [preroll, setPreroll] = useState(null);
  const centerTimerRef = useRef(null);
  const osdOpenRef = useRef(true);

  const key = String(ratingKey || "").trim();
  if (key !== playerKey) {
    // Same player instance, new episode. Clear the end card before paint so the
    // next watch route can attach a stream instead of sitting on a dead card.
    setPlayerKey(key);
    setEnded(false);
    setEndNote("");
    setError("");
    setResumeOpen(false);
    setPreroll(null);
    setSession(null);
    setSeekEpoch(0);
    setPictureHold(false);
    setHoldFrame("");
    pictureHoldRef.current = false;
    seekTimelineOriginRef.current = 0;
  }

  // One subtitle model: real Plex tracks (embedded + sidecar) for the item being played,
  // fetched through the authenticated proxy and drawn by Projectionist.
  const subtitleKey = String(session?.rating_key || "").trim();
  const [subTracks, setSubTracks] = useState([]);
  const [subListNote, setSubListNote] = useState("");
  const [activeSub, setActiveSub] = useState(-1);
  const [subDelay, setSubDelay] = useState(0);
  const [burnInTracks, setBurnInTracks] = useState([]);
  const activeSubTrack = subTracks.find((track) => track.index === activeSub) || null;
  const activeBurnIn = burnInTracks.find((track) => track.index === activeSub) || null;
  const subs = useSubtitleCues(activeBurnIn ? "" : activeSubTrack?.proxyUrl || "");
  const subPresentation = resolveSubtitlePresentation({
    softTrackSelected: Boolean(activeSubTrack?.proxyUrl) && !activeBurnIn,
    softTrackReady: subs.state === "ready",
    burnInSelected: Boolean(activeBurnIn),
  });
  /** Absolute title seconds (includes 0-based seek origin) so delay/sync match the picture. */
  const getSubtitleTimeSec = useCallback(() => {
    const video = videoRef.current;
    if (!video) return Number.NaN;
    return (
      playheadMsFromMedia({
        currentTimeSec: video.currentTime || 0,
        originMs: seekTimelineOriginRef.current,
      }) / 1000
    );
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    const hls = hlsRef.current;
    if (hls && typeof hls.subtitleTrack === "number") {
      hls.subtitleTrack = -1;
    }
    if (subPresentation.disableAllNative) silenceNativeTextTracks(video);
  }, [subPresentation.disableAllNative, activeSub, seekEpoch, session?.stream_url]);

  useEffect(() => {
    setActiveSub(-1);
    setSubDelay(0);
    setSubTracks([]);
    setBurnInTracks([]);
    setSubListNote("");
    if (!subtitleKey) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const listed = await getLibraryItemSubtitles(subtitleKey);
        if (cancelled) return;
        const preferred = listed?.preferred_languages || ["en"];
        let downloaded = null;
        let downloadMessage = "";
        const first = resolvePlaySubtitleTracks({
          listedStreams: listed?.streams,
          preferredLanguages: preferred,
        });
        if (first.needsFetch) {
          setSubListNote("Looking for text captions…");
          try {
            const result = await downloadLibraryItemSubtitles(subtitleKey);
            if (cancelled) return;
            downloadMessage = String(result?.message || "");
            downloaded = Array.isArray(result?.streams) ? result.streams : [];
            if (result?.ok && !downloaded.length) {
              const refreshed = await getLibraryItemSubtitles(subtitleKey);
              if (cancelled) return;
              downloaded = refreshed?.streams ?? [];
            }
          } catch {
            downloadMessage = "Plex couldn’t find text captions for this title.";
          }
        }
        if (cancelled) return;
        const resolved = resolvePlaySubtitleTracks({
          listedStreams: listed?.streams,
          downloadedStreams: downloaded,
          preferredLanguages: preferred,
        });
        setSubTracks(resolved.tracks);
        setBurnInTracks(resolved.burnInTracks);
        if (resolved.autoSelectIndex !== -1) setActiveSub(resolved.autoSelectIndex);
        if (resolved.empty && !resolved.burnInTracks.length) {
          setSubListNote(
            downloadMessage ||
              (listed?.ok === false ? listed?.message || "" : listed?.streams?.length
                ? SUBTITLE_NO_TEXT_TRACKS
                : SUBTITLE_EMPTY_TRACKS),
          );
        } else {
          setSubListNote("");
        }
      } catch {
        if (!cancelled) setSubListNote("Couldn’t read subtitle tracks for this title.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subtitleKey]);

  function selectSubtitle(track) {
    const current = sessionRef.current;
    const offsetMs = displayedPlayheadMs();
    const wasBurnIn = Boolean(activeBurnIn);
    if (!track || track.index === -1) {
      setActiveSub(-1);
      if (wasBurnIn && current?.session_id) {
        void restartPlaybackCaptions(null, offsetMs);
      }
      return;
    }
    if (track.burnIn) {
      if (activeBurnIn?.id === track.id) return;
      setActiveSub(track.index);
      setSubDelay(0);
      if (current?.session_id) {
        void restartPlaybackCaptions(track.id, offsetMs);
      }
      return;
    }
    if (!track.renderable) return;
    setActiveSub(track.index);
    if (wasBurnIn && current?.session_id) {
      void restartPlaybackCaptions(null, offsetMs);
    }
  }

  useEffect(() => {
    const syncViewport = () => {
      setPhone(isPhonePlayViewport());
      setCompact(isCompactPlayViewport());
      setLongSkip(longSkipFits({ width: window.innerWidth, height: window.innerHeight }));
    };
    const onResize = () => syncViewport();
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    setPipSupported(Boolean(document.pictureInPictureEnabled));
    syncViewport();
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
      if (seekRestartTimerRef.current) {
        window.clearTimeout(seekRestartTimerRef.current);
        seekRestartTimerRef.current = null;
      }
      if (seekPaintTimerRef.current) {
        window.clearTimeout(seekPaintTimerRef.current);
        seekPaintTimerRef.current = null;
      }
      scrubCommitRef.current?.cancel();
    };
  }, []);

  const stopSession = useCallback(async (extra = {}) => {
    const current = sessionRef.current;
    if (!current?.session_id) return;
    const video = videoRef.current;
    try {
      const timeMs = extra.time_ms ?? playheadMsFromMedia({
        currentTimeSec: video?.currentTime || 0,
        originMs: seekTimelineOriginRef.current,
      });
      const durationMs = extra.duration_ms ?? Math.round((video?.duration || 0) * 1000);
      await stopLibraryPlayback(current.session_id, {
        time_ms: timeMs,
        duration_ms: durationMs,
      });
      rememberPlayedProgress(current, timeMs, durationMs);
    } catch {
      // Best-effort — unmount / hide still tears down local state.
    }
    if (sessionRef.current === current) sessionRef.current = null;
  }, []);

  const handlePlayerStatus = useCallback((next) => {
    setStatus(next);
    if (next === "playing") {
      if (centerTimerRef.current) {
        window.clearTimeout(centerTimerRef.current);
        centerTimerRef.current = null;
      }
      setCenterPlayOn(false);
    } else if (next === "paused" && !osdOpenRef.current) {
      const hold = centerPlayHoldAfterOsdHide({ paused: true });
      setCenterPlayOn(hold.visible);
      if (centerTimerRef.current) window.clearTimeout(centerTimerRef.current);
      if (hold.hideAfterMs > 0) {
        centerTimerRef.current = window.setTimeout(() => setCenterPlayOn(false), hold.hideAfterMs);
      }
    }
    if (next === "playing") {
      // Manifest "ready" is not a frame. A seek hold clears only from onPictureReady.
      if (pictureHoldRef.current) return;
      setSeeking(false);
      if (!seekFailedRef.current) setError("");
    } else if (next === "error") {
      if (pictureHoldRef.current && seekReloadArmedRef.current) {
        void failSeekRef.current(SEEK_FAILED_MESSAGE);
        return;
      }
      if (!pictureHoldRef.current) {
        setSeeking(false);
        setError((prev) => prev || "Playback stalled. Try Resume, refresh, or Open in Plex.");
      }
    }
  }, []);

  const onOsdVisibility = useCallback((open) => {
    osdOpenRef.current = open;
    setOsdOpen(open);
    if (open) {
      if (centerTimerRef.current) {
        window.clearTimeout(centerTimerRef.current);
        centerTimerRef.current = null;
      }
      setCenterPlayOn(true);
      return;
    }
    const video = videoRef.current;
    const paused = Boolean(video && video.paused && !video.ended);
    const hold = centerPlayHoldAfterOsdHide({ paused });
    if (!hold.visible) {
      setCenterPlayOn(false);
      return;
    }
    setCenterPlayOn(true);
    if (centerTimerRef.current) window.clearTimeout(centerTimerRef.current);
    centerTimerRef.current = window.setTimeout(() => setCenterPlayOn(false), hold.hideAfterMs);
  }, []);

  useEffect(() => () => {
    if (centerTimerRef.current) window.clearTimeout(centerTimerRef.current);
  }, []);

  const handleHlsRef = useCallback((hls) => {
    hlsRef.current = hls;
  }, []);

  const handleVideoRef = useCallback((el) => {
    videoRef.current = el;
  }, []);

  const begin = useCallback(
    async ({ startOver = false } = {}) => {
      if (!key || startingRef.current) return;
      if (!startOver && sessionRef.current?.stream_url) {
        setResumeOpen(false);
        setEnded(false);
        setStatus("ready");
        return;
      }
      startingRef.current = true;
      setStartBusy(true);
      setError("");
      setEnded(false);
      setStatus("loading");
      try {
        if (sessionRef.current?.session_id && startOver) {
          try {
            await stopLibraryPlayback(sessionRef.current.session_id, { time_ms: 0 });
            rememberPlayedProgress(sessionRef.current, 0, Number(sessionRef.current.duration_ms) || 0);
          } catch {
            // replace the session below
          }
          sessionRef.current = null;
        }
        const payload = await startLibraryPlayback(key, { startOver });
        sessionRef.current = payload;
        setSession(payload);
        seekTimelineOriginRef.current = 0;
        seekCommittedMsRef.current = null;
        setSeekEpoch(0);
        setDurationMs(Number(payload.duration_ms) || 0);
        setNowMs(startOver ? 0 : Number(payload.view_offset_ms) || 0);
        setResumeOpen(false);
        // Movie start-over (or cold start without resume gate) gets a host bumper.
        if (shouldPlayMoviePreroll(payload) && (startOver || !Number(payload.view_offset_ms))) {
          try {
            const bumper = normalizePrerollPayload(await fetchNextPreroll("movie"));
            setPreroll(bumper);
          } catch {
            setPreroll(null);
          }
        } else {
          setPreroll(null);
        }
        setStatus("ready");
      } catch (err) {
        setError(err?.message || "This title couldn’t start in Projectionist.");
        setStatus("error");
      } finally {
        startingRef.current = false;
        setStartBusy(false);
      }
    },
    [key],
  );

  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      try {
        const payload = await startLibraryPlayback(key, { startOver: false });
        if (cancelled) {
          try {
            await stopLibraryPlayback(payload.session_id, {});
          } catch {
            // ignore
          }
          return;
        }
        sessionRef.current = payload;
        seekTimelineOriginRef.current = 0;
        seekCommittedMsRef.current = null;
        setSeekEpoch(0);
        setDurationMs(Number(payload.duration_ms) || 0);
        const continueAt = continueAtMsRef.current;
        const restoring = continueAt != null && Number.isFinite(Number(continueAt));
        if (restoring) {
          const target = Math.max(0, Math.floor(Number(continueAt) || 0));
          let active = payload;
          const plexOffset = Number(payload.view_offset_ms) || 0;
          if (payload.session_id && Math.abs(plexOffset - target) > 1500) {
            try {
              active = await seekLibraryPlayback(payload.session_id, target);
            } catch {
              // Play already started a session; keep that position if the seek fails.
            }
          }
          if (cancelled) {
            try {
              await stopLibraryPlayback(active?.session_id || payload.session_id, {});
            } catch {
              // ignore
            }
            return;
          }
          sessionRef.current = active;
          setSession(active);
          setDurationMs(Number(active?.duration_ms) || Number(payload.duration_ms) || 0);
          setNowMs(target);
          setResumeOpen(false);
          setPreroll(null);
          setStatus("ready");
        } else {
          setSession(payload);
          setNowMs(Number(payload.view_offset_ms) || 0);
          if (shouldResumeFromOffset(payload.view_offset_ms) && payload.can_resume) {
            setResumeOpen(true);
            setStatus("paused");
          } else {
            if (shouldPlayMoviePreroll(payload) && !Number(payload.view_offset_ms)) {
              try {
                const bumper = normalizePrerollPayload(await fetchNextPreroll("movie"));
                if (!cancelled) setPreroll(bumper);
              } catch {
                if (!cancelled) setPreroll(null);
              }
            }
            setStatus("ready");
          }
        }
      } catch (err) {
        if (!cancelled) {
          const message = err?.message || "This title couldn’t start in Projectionist.";
          setError(message);
          setStatus("error");
          if (autoplayNextRef.current) {
            setEndNote(message);
            setEnded(true);
          }
        }
      }
    })();
    return () => {
      cancelled = true;
      stopSession();
    };
  }, [key, stopSession]);

  useEffect(() => {
    function refreshPref() {
      pauseWhenBackgroundedRef.current = loadPauseWhenBackgrounded();
      setBlackFrame(loadPlayBlackFrame());
    }
    refreshPref();
    window.addEventListener("storage", refreshPref);
    window.addEventListener(UI_PREFS_CHANGED_EVENT, refreshPref);
    return () => {
      window.removeEventListener("storage", refreshPref);
      window.removeEventListener(UI_PREFS_CHANGED_EVENT, refreshPref);
    };
  }, []);

  useEffect(() => {
    async function resumeAfterVisible() {
      const video = videoRef.current;
      const streamUrl = sessionRef.current?.stream_url || session?.stream_url || "";
      if (!canResumeAttachedStream({ video, streamUrl })) {
        await begin({ startOver: false });
        return;
      }
      try {
        hlsRef.current?.startLoad?.();
        await video.play();
        setStatus("playing");
      } catch {
        setStatus("paused");
      }
    }

    function onVisibility() {
      const state = document.visibilityState;
      const pausePref = pauseWhenBackgroundedRef.current;
      const video = videoRef.current;
      const playing = Boolean(video && !video.paused && !video.ended);

      if (state === "hidden") {
        const remembered = notePlayingBeforeHide({ playing, visibilityState: state });
        if (remembered != null) wasPlayingBeforeHideRef.current = remembered;
        // Default: keep buffering/playing through Mac Spaces / tab hide.
        // Opt-in: soft-pause without killing the Plex session.
        if (
          shouldPauseOnVisibilityHide({ pauseWhenBackgrounded: pausePref, visibilityState: state })
        ) {
          if (video && !video.paused) {
            video.pause();
            hlsRef.current?.stopLoad?.();
            setStatus("paused");
            sendProgress("paused", video);
          }
        }
        return;
      }

      if (
        shouldAutoResumePlayback({
          wasPlaying: wasPlayingBeforeHideRef.current,
          visibilityState: state,
        })
      ) {
        // Recover when opt-in paused us, or when the browser forced a pause.
        if (pausePref || (video && video.paused)) {
          wasPlayingBeforeHideRef.current = false;
          resumeAfterVisible();
        } else {
          wasPlayingBeforeHideRef.current = false;
        }
      }
    }

    function onPageHide(event) {
      // Flush shrunk playhead whenever we leave the foreground.
      if (floatedRef.current) {
        const video = videoRef.current;
        onPlayheadRef.current?.({
          offsetMs: Math.round((video?.currentTime || 0) * 1000),
          title: displayTitle(sessionRef.current),
          flush: true,
        });
      }
      // iPad Safari fires pagehide on lock / app switch with persisted=true (bfcache).
      // Keep the session so pageshow can resume open→resume→done.
      if (!shouldStopSessionOnPageHide({ persisted: Boolean(event?.persisted) })) {
        return;
      }
      // Real navigation / close — free the transcoder.
      stopSession();
    }

    function onPageShow(event) {
      if (
        !shouldResumeOnPageShow({
          persisted: Boolean(event?.persisted),
          wasPlaying: wasPlayingBeforeHideRef.current,
        })
      ) {
        return;
      }
      wasPlayingBeforeHideRef.current = false;
      resumeAfterVisible();
    }

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("pageshow", onPageShow);
    };
    // begin / sendProgress / session are stable enough via refs for this lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- visibility controller
  }, [stopSession]);

  useEffect(() => {
    function onWindowKey(event) {
      // Focused player (and its scrubber) already receive keydown on the stage.
      const root = document.querySelector("[data-testid='library-player']");
      if (root?.contains(event.target)) return;
      dispatchLibraryPlayKey(event, playKeyRef.current);
    }
    window.addEventListener("keydown", onWindowKey);
    return () => window.removeEventListener("keydown", onWindowKey);
  }, []);

  async function sendProgress(state, video) {
    const current = sessionRef.current;
    if (!current?.session_id) return;
    const now = Date.now();
    if (state !== "stopped" && state !== "paused" && !shouldSendProgress(lastProgressAtRef.current, now)) return;
    lastProgressAtRef.current = now;
    const timeMs = playheadMsFromMedia({
      currentTimeSec: video?.currentTime || 0,
      originMs: seekTimelineOriginRef.current,
    });
    const reportedDuration = Math.round((video?.duration || durationMs / 1000 || 0) * 1000);
    try {
      await progressLibraryPlayback(current.session_id, {
        state,
        time_ms: timeMs,
        duration_ms: reportedDuration,
      });
      rememberPlayedProgress(current, timeMs, reportedDuration);
    } catch {
      // Progress is best-effort.
    }
  }

  function applyLocalSkip(deltaSeconds) {
    const video = videoRef.current;
    if (!video) return;
    const next = clampTime(
      (video.currentTime || 0) + deltaSeconds,
      video.duration || durationMs / 1000,
    );
    try {
      video.currentTime = next;
    } catch {
      // Some browsers reject currentTime before metadata.
    }
    setNowMs(playheadMsFromMedia({
      currentTimeSec: next,
      originMs: seekTimelineOriginRef.current,
    }));
    const label = deltaSeconds < 0 ? `−${Math.abs(deltaSeconds)}s` : `+${deltaSeconds}s`;
    setSkipChip(label);
    window.setTimeout(() => setSkipChip(""), 900);
  }

  function displayedPlayheadMs() {
    const video = videoRef.current;
    return playheadMsFromMedia({
      currentTimeSec: video?.currentTime || 0,
      originMs: seekTimelineOriginRef.current,
    });
  }

  function clearSeekPaintTimer() {
    if (seekPaintTimerRef.current) {
      window.clearTimeout(seekPaintTimerRef.current);
      seekPaintTimerRef.current = null;
    }
  }

  function armSeekPaintTimer() {
    clearSeekPaintTimer();
    seekPaintTimerRef.current = window.setTimeout(() => {
      seekPaintTimerRef.current = null;
      void failSeekRef.current(SEEK_FAILED_MESSAGE);
    }, SEEK_PICTURE_TIMEOUT_MS);
  }

  function holdSeekPicture() {
    const video = videoRef.current;
    if (!pictureHoldRef.current) {
      savedMutedRef.current = Boolean(video?.muted);
      wasPlayingRef.current = video ? !video.paused : true;
      setHoldFrame(capturePlaybackHoldFrame(video));
    }
    pictureHoldRef.current = true;
    setPictureHold(true);
    if (video) {
      try {
        video.pause();
      } catch {
        // Ignore pause races while the element is being swapped.
      }
      video.muted = true;
    }
  }

  function releaseSeekPicture() {
    const video = videoRef.current;
    pictureHoldRef.current = false;
    setPictureHold(false);
    setHoldFrame("");
    clearSeekPaintTimer();
    if (video) video.muted = savedMutedRef.current;
  }

  function handlePictureReady() {
    if (!pictureHoldRef.current) return;
    const video = videoRef.current;
    seekTimelineOriginRef.current = seekTimelineOriginMs({
      currentTimeSec: video?.currentTime,
      committedOffsetMs: seekCommittedMsRef.current,
    });
    const failed = seekFailedRef.current;
    releaseSeekPicture();
    setSeeking(false);
    if (!failed) setError("");
    if (!video) return;
    if (wasPlayingRef.current) {
      if (video.paused) video.play?.().catch(() => {});
    } else {
      video.pause();
    }
  }

  async function failSeek(message) {
    if (seekFailingRef.current) return;
    seekFailingRef.current = true;
    const text = message || SEEK_FAILED_MESSAGE;
    setError(text);
    seekFailedRef.current = true;
    clearSeekPaintTimer();
    const current = sessionRef.current;
    const restore = seekRestoreMsRef.current;
    if (!seekRestoreAttemptedRef.current && current?.session_id && restore != null) {
      seekRestoreAttemptedRef.current = true;
      try {
        const next = await seekLibraryPlayback(current.session_id, restore);
        sessionRef.current = next;
        setSession(next);
        setNowMs(restore);
        seekCommittedMsRef.current = restore;
        seekReloadArmedRef.current = true;
        holdSeekPicture();
        setSeekEpoch((epoch) => epoch + 1);
        armSeekPaintTimer();
        seekFailingRef.current = false;
        return;
      } catch {
        // The previous position could not be reopened either.
      }
    }
    seekReloadArmedRef.current = false;
    releaseSeekPicture();
    setSeeking(false);
    setStatus("paused");
    seekFailingRef.current = false;
  }

  failSeekRef.current = failSeek;

  async function applySeekRestartNow(offsetMs) {
    const current = sessionRef.current;
    if (!current?.session_id) {
      releaseSeekPicture();
      setSeeking(false);
      return;
    }
    seekCommittedMsRef.current = offsetMs;
    setSeeking(true);
    try {
      const next = await seekLibraryPlayback(current.session_id, offsetMs);
      sessionRef.current = next;
      setSession(next);
      setNowMs(offsetMs);
      rememberPlayedProgress(next, offsetMs, Number(next.duration_ms) || durationMs);
      seekReloadArmedRef.current = true;
      setSeekEpoch((epoch) => epoch + 1);
      armSeekPaintTimer();
    } catch (err) {
      await failSeek(err?.message || SEEK_FAILED_MESSAGE);
    }
  }

  /** Debounce Plex session-restart seeks from scrub / skip spam. */
  function applySeekRestart(offsetMs) {
    if (!pictureHoldRef.current) {
      const playingMs = displayedPlayheadMs();
      seekRestoreMsRef.current = playingMs > 0 ? playingMs : Math.max(0, Math.round(nowMs));
      seekRestoreAttemptedRef.current = false;
      seekFailedRef.current = false;
      seekReloadArmedRef.current = false;
      holdSeekPicture();
    }
    seekRestartPendingMsRef.current = offsetMs;
    setSeeking(true);
    if (seekRestartTimerRef.current) {
      window.clearTimeout(seekRestartTimerRef.current);
    }
    seekRestartTimerRef.current = window.setTimeout(() => {
      seekRestartTimerRef.current = null;
      const pending = seekRestartPendingMsRef.current;
      seekRestartPendingMsRef.current = null;
      if (pending == null) return;
      void applySeekRestartNow(pending);
    }, SEEK_RESTART_DEBOUNCE_MS);
  }

  /** Switching to/from Plex burn-in restarts the transcode at the playhead. */
  async function restartPlaybackCaptions(subtitleStreamId, offsetMs) {
    const current = sessionRef.current;
    if (!current?.session_id) return;
    const target = Math.max(0, Math.floor(Number(offsetMs) || 0));
    if (!pictureHoldRef.current) {
      seekRestoreMsRef.current = target;
      seekRestoreAttemptedRef.current = false;
      seekFailedRef.current = false;
      seekReloadArmedRef.current = false;
      holdSeekPicture();
    }
    seekCommittedMsRef.current = target;
    setSeeking(true);
    try {
      const next = await setLibraryPlaybackSubtitles(current.session_id, {
        subtitleStreamId,
        offsetMs: target,
      });
      sessionRef.current = next;
      setSession(next);
      setNowMs(target);
      seekReloadArmedRef.current = true;
      setSeekEpoch((epoch) => epoch + 1);
      armSeekPaintTimer();
    } catch (err) {
      await failSeek(err?.message || SEEK_FAILED_MESSAGE);
    }
  }

  /** Local currentTime when buffered; otherwise Plex session restart at offset. */
  function seekToOffsetMs(offsetMs) {
    const video = videoRef.current;
    const durationS = video?.duration || durationMs / 1000;
    const target = clampTime(offsetMs / 1000, durationS);
    const targetMs = Math.round(target * 1000);
    if (video && canLocalSeekTo(video, target) && !seekReloadArmedRef.current) {
      if (seekRestartTimerRef.current) {
        window.clearTimeout(seekRestartTimerRef.current);
        seekRestartTimerRef.current = null;
        seekRestartPendingMsRef.current = null;
      }
      if (pictureHoldRef.current) {
        releaseSeekPicture();
        setSeeking(false);
      }
      try {
        video.currentTime = target;
      } catch {
        // Some browsers reject currentTime before metadata.
      }
      setNowMs(playheadMsFromMedia({
        currentTimeSec: target,
        originMs: seekTimelineOriginRef.current,
      }));
      return;
    }
    applySeekRestart(targetMs);
  }

  function skipBy(deltaSeconds, { preferLocal = true } = {}) {
    const video = videoRef.current;
    const titleDuration = durationMs > 0 ? durationMs / 1000 : 0;
    const duration = titleDuration || video?.duration || 0;
    const originSec = seekTimelineOriginRef.current / 1000;
    const mediaNow = video?.currentTime || 0;
    const displayNow = mediaNow + originSec || nowMs / 1000;
    const targetDisplay = clampTime(displayNow + deltaSeconds, duration);
    const targetMedia = Math.max(0, targetDisplay - originSec);
    const inBuffer = canLocalSeekTo(video, targetMedia);
    if (preferLocal && video && (Math.abs(deltaSeconds) <= SKIP_SECONDS || inBuffer)) {
      applyLocalSkip(deltaSeconds);
      return;
    }
    applySeekRestart(Math.round(targetDisplay * 1000));
    const label = deltaSeconds < 0 ? `−${Math.abs(deltaSeconds)}s` : `+${deltaSeconds}s`;
    setSkipChip(label);
    window.setTimeout(() => setSkipChip(""), 900);
  }

  function scrubDurationMs() {
    return durationMs || Math.round((videoRef.current?.duration || 0) * 1000);
  }

  function previewScrub(pct) {
    const duration = scrubDurationMs();
    setScrubPct(pct);
    if (duration) setNowMs(msFromScrubPct(pct, duration));
  }

  commitScrubRef.current = (pct) => {
    scrubbingRef.current = false;
    setScrubPct(null);
    const duration = scrubDurationMs();
    if (!duration) return;
    seekToOffsetMs(msFromScrubPct(pct, duration));
  };

  if (!scrubCommitRef.current) {
    scrubCommitRef.current = createScrubCommit({
      onCommit: (pct) => commitScrubRef.current(pct),
    });
  }

  function beginScrub(event) {
    // Do not setPointerCapture. On iPad Safari, capturing the range input
    // steals the gesture and pointerup never arrives, so the scrub flag stays
    // set and playback stops updating.
    scrubbingRef.current = true;
    const pct = Number(event.target.value);
    previewScrub(pct);
    scrubCommitRef.current.begin();
    scrubCommitRef.current.input(pct);
  }

  function onScrubInput(event) {
    scrubbingRef.current = true;
    const pct = Number(event.target.value);
    previewScrub(pct);
    scrubCommitRef.current.input(pct);
  }

  function endScrub() {
    scrubCommitRef.current.end();
  }

  async function togglePlayback() {
    if (pictureHoldRef.current) return;
    if (status === "loading" || status === "error" || resumeOpen) return;
    const video = videoRef.current;
    // If the stream was cleared (pagehide / failed attach), Play re-arms via begin()
    // instead of no-op play() on an empty <video>.
    if (!video || (!video.currentSrc && !session?.stream_url && !sessionRef.current?.stream_url)) {
      await begin({ startOver: false });
      return;
    }
    if (video.paused) {
      try {
        await video.play();
        setStatus("playing");
      } catch {
        setStatus("paused");
      }
    } else {
      video.pause();
      setStatus("paused");
      sendProgress("paused", video);
    }
  }

  playKeyRef.current = { skipBy, togglePlayback };

  async function enterPiP() {
    const video = videoRef.current;
    if (!video?.requestPictureInPicture) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else {
        await video.requestPictureInPicture();
      }
    } catch {
      // PiP can be blocked; fullscreen remains.
    }
  }

  function openPopout() {
    if (phone || !key) return;
    const href = libraryWatchPopoutPath(key);
    const features = "popup=yes,width=960,height=540,menubar=no,toolbar=no,location=no,status=no";
    const popup = window.open(href, "projectionist-library-watch", features);
    if (!popup) return;
    stopSession();
    if (onAfterPopout) onAfterPopout();
    else navigate(-1);
  }

  function shrinkOntoPageClick() {
    const from = typeof location.state?.from === "string" ? location.state.from : "";
    const next = shrinkOntoPage(videoRef.current, {
      ratingKey: key,
      returnTo: from,
      title: displayTitle(sessionRef.current),
    });
    onShrink?.(next);
  }

  function leaveWatch() {
    setMoreOpen(false);
    stopSession();
    if (popout) {
      window.close();
      return;
    }
    navigate(-1);
  }

  function toggleFullscreen() {
    const root = document.querySelector("[data-testid='library-player']");
    toggleTheaterFullscreen(root, { video: videoRef.current });
  }

  function handleStageActivate(_event, _zone) {
    const video = videoRef.current;
    if (pendingUnmuteRef.current && video?.muted) {
      delete video.dataset?.shrunkHoldMute;
      video.muted = false;
      pendingUnmuteRef.current = false;
      if (video.paused) video.play?.().catch(() => {});
      return;
    }
    togglePlayback();
  }

  function handleStageDoubleActivate(_event, zone) {
    const delta = skipDeltaForZone(zone);
    if (delta) {
      skipBy(delta);
      return;
    }
    toggleFullscreen();
  }

  function handleKeyDown(event, { toggleFullscreen: fs, video }) {
    if (isPlayShortcutBlockedTarget(event.target)) return;
    if (dispatchLibraryPlayKey(event, { skipBy, togglePlayback })) return;
    const action = theaterKeyAction(event.key);
    if (!action) return;
    if (action === "mute") {
      event.preventDefault();
      if (video) video.muted = !video.muted;
    } else if (action === "captions") {
      event.preventDefault();
      setCcOpen((open) => !open);
      setMoreOpen(false);
    } else if (action === "escape") {
      event.preventDefault();
      if (moreOpen) {
        setMoreOpen(false);
        return;
      }
      if (ccOpen) {
        setCcOpen(false);
        return;
      }
      if (isDocumentFullscreen()) {
        const root = document.querySelector("[data-testid='library-player']");
        toggleTheaterFullscreen(root, { video: videoRef.current });
        return;
      }
      {
        const root = document.querySelector("[data-testid='library-player']");
        if (root?.classList.contains("theater-player--immersive") || videoRef.current?.webkitDisplayingFullscreen) {
          toggleTheaterFullscreen(root, { video: videoRef.current });
          return;
        }
      }
      leaveWatch();
    } else if (action === "fullscreen") {
      fs?.();
    }
  }

  const plexHref = session?.plex_watch_url || "";
  const next = session?.next_episode;
  const nextDecision = nextEpisodeEndCardAction(next, key);
  const endCardMessage = endNote || (nextDecision.action === "message" ? nextDecision.message : "");

  function playNextEpisode() {
    runNextEpisodeEndCard(next, key, {
      navigate: (path) => navigate(path, { state: { autoplayNext: true } }),
      onMessage: setEndNote,
    });
  }

  function backToExplore() {
    stopSession();
    runEndCardBackToExplore({ navigate });
  }
  const showOsd = !resumeOpen && !ended;
  const playing = status === "playing";
  const showCenterPlay =
    showOsd && !playing && !error && status !== "loading" && Boolean(session) && centerPlayOn;
  const pausedFrameClean =
    Boolean(session) && status === "paused" && !osdOpen && !centerPlayOn && !resumeOpen && !ended;
  const closePlace = playerClosePlacement();
  const durationS = durationMs / 1000 || 0;
  const bufferedPct = durationS ? Math.round((bufferedEndS / durationS) * 100) : 0;
  const playheadPct = scrubPctFromMs(nowMs, durationMs);
  const sliderPct = scrubPct != null ? scrubPct : playheadPct;
  const headline = displayHeadline(session);
  const metaLine = displayMeta(session);
  const forceOsd = moreOpen || ccOpen;
  const barActions = playerBarActions({
    presentation: floated ? "pip" : "stage",
    popoutWindow: popout,
    phone,
  });

  const osd = showOsd ? (
    <LibraryPlayerOsd
      popout={popout}
      headline={headline}
      metaLine={metaLine}
      nowMs={nowMs}
      durationMs={durationMs}
      bufferedPct={bufferedPct}
      sliderPct={sliderPct}
      longSkip={longSkip}
      playing={playing}
      ccOpen={ccOpen}
      moreOpen={moreOpen}
      barActions={barActions}
      closePlace={closePlace}
      pipSupported={pipSupported}
      plexHref={plexHref}
      blackFrame={blackFrame}
      subTracks={subTracks}
      burnInTracks={burnInTracks}
      activeSub={activeSub}
      activeSubTrack={activeSubTrack}
      subs={subs}
      subListNote={subListNote}
      subDelay={subDelay}
      activeBurnIn={activeBurnIn}
      onSkipBy={skipBy}
      onTogglePlayback={togglePlayback}
      onBeginScrub={beginScrub}
      onEndScrub={endScrub}
      onScrubInput={onScrubInput}
      onToggleCc={() => {
        setCcOpen((open) => !open);
        setMoreOpen(false);
      }}
      onShrink={shrinkOntoPageClick}
      onFullscreen={toggleFullscreen}
      onLeaveWatch={leaveWatch}
      onToggleMore={() => {
        setMoreOpen((open) => !open);
        setCcOpen(false);
      }}
      onCloseMore={() => setMoreOpen(false)}
      onEnterPiP={enterPiP}
      onOpenPopout={openPopout}
      onToggleBlackFrame={() => setBlackFrame(persistPlayBlackFrame(!blackFrame))}
      onSelectSubtitle={selectSubtitle}
      onDelayChange={setSubDelay}
    />
  ) : null;

  return (
    <div
      className={`library-watch ${phone ? "library-watch--phone" : ""} ${compact ? "library-watch--compact" : ""} ${className}`.trim()}
      data-play-phone={phone ? "true" : "false"}
      data-play-compact={compact ? "true" : "false"}
      data-play-frame={blackFrame ? "black" : "art"}
      data-long-skip={longSkip ? "true" : "false"}
      data-center-play={showCenterPlay ? "visible" : "hidden"}
    >
      <TheaterPlayer
        src={
          resumeOpen || ended || preroll || !session?.stream_url
            ? ""
            : playbackSrcForSeek(session.stream_url, seekEpoch)
        }
        poster={session?.poster_url || ""}
        className="library-player"
        blackFrame={blackFrame}
        testId="library-player"
        videoTestId="library-player-video"
        loading={status === "loading" && !resumeOpen && !preroll}
        pictureHold={pictureHold}
        holdFrame={holdFrame}
        onPictureReady={handlePictureReady}
        loadingCopy="warming the reel"
        error=""
        osd={osd}
        osdVisible={forceOsd ? true : undefined}
        onStatus={handlePlayerStatus}
        onVideoRef={handleVideoRef}
        onHlsRef={handleHlsRef}
        resumeMutedIfBlocked={continueAtMs != null}
        onAutoplayResult={(result) => {
          pendingUnmuteRef.current = Boolean(result?.unmuteOnTap && result?.playing);
        }}
        onTimeUpdate={(video) => {
          if (!scrubbingRef.current && !pictureHoldRef.current) {
            setNowMs(playheadMsFromMedia({
              currentTimeSec: video.currentTime || 0,
              originMs: seekTimelineOriginRef.current,
            }));
          }
          if (video.duration) setDurationMs(Math.round(video.duration * 1000));
          const ranges = bufferedRanges(video);
          setBufferedEndS(ranges[ranges.length - 1]?.end || 0);
          if (!scrubbingRef.current) sendProgress("playing", video);
          if (floatedRef.current) {
            onPlayheadRef.current?.({
              offsetMs: Math.round((video.currentTime || 0) * 1000),
              title: displayTitle(sessionRef.current),
            });
          }
        }}
        onEnded={() => {
          setEnded(true);
          setMoreOpen(false);
          sendProgress("stopped", videoRef.current);
        }}
        onStageActivate={handleStageActivate}
        onStageDoubleActivate={handleStageDoubleActivate}
        onKeyDown={handleKeyDown}
        onOsdVisibility={onOsdVisibility}
        pausedFrameClean={pausedFrameClean}
        holdToDoubleSpeed
        bufferingEnabled={!error && !resumeOpen && !ended && !preroll}
      >
        {subPresentation.showOverlay ? (
          <SubtitleOverlay
            cues={subs.cues}
            getTimeSec={getSubtitleTimeSec}
            delaySec={subDelay}
            testId="library-subtitle-overlay"
          />
        ) : null}
        {preroll ? <PrerollStage src={preroll.url} onDone={() => setPreroll(null)} /> : null}
        {showCenterPlay ? (
          <button
            type="button"
            className="theater-center-play"
            onClick={togglePlayback}
            aria-label="Play"
            data-testid="library-center-play"
            data-theater-chrome="true"
          >
            <span className="theater-center-play-glyph" aria-hidden="true">
              ▶
            </span>
          </button>
        ) : null}

        {skipChip ? (
          <div className="theater-skip-chip" role="status" data-testid="library-skip-chip">
            {skipChip}
          </div>
        ) : null}

        {resumeOpen ? (
          <div className="theater-resume-gate" data-testid="library-resume-gate">
            <div className="theater-resume-copy">
              <p className="theater-resume-kicker">Continue watching</p>
              <p className="theater-resume-title">{displayTitle(session)}</p>
              <p className="theater-resume-offset muted">
                From {formatClockMs(Number(session?.view_offset_ms) || nowMs)}
              </p>
            </div>
            <div className="theater-resume-actions">
              <button
                type="button"
                className="title-cta title-cta-primary"
                disabled={startBusy}
                onClick={() => begin({ startOver: false })}
              >
                Resume
              </button>
              <button
                type="button"
                className="title-cta title-cta-ghost"
                disabled={startBusy}
                onClick={() => begin({ startOver: true })}
              >
                Start over
              </button>
            </div>
          </div>
        ) : null}

        {ended ? (
          <div
            className="theater-end-card"
            data-testid="library-end-card"
            data-theater-chrome="true"
          >
            <p className="theater-end-kicker">That’s the reel</p>
            {endCardMessage ? (
              <p
                className="theater-end-note"
                role="status"
                data-testid="library-next-episode-message"
              >
                {endCardMessage}
              </p>
            ) : null}
            <div className="theater-resume-actions">
              {endNote && error ? (
                <button
                  type="button"
                  className="title-cta title-cta-primary"
                  disabled={startBusy}
                  onClick={() => begin({ startOver: false })}
                >
                  Try again
                </button>
              ) : nextDecision.action === "play" ? (
                <button
                  type="button"
                  className="title-cta title-cta-primary"
                  onClick={playNextEpisode}
                  data-testid="library-next-episode"
                >
                  Next episode
                </button>
              ) : null}
              {nextDecision.action !== "play" || (endNote && error) ? (
                <button
                  type="button"
                  className={
                    endNote && error ? "title-cta title-cta-ghost" : "title-cta title-cta-primary"
                  }
                  onClick={leaveWatch}
                >
                  Back to title
                </button>
              ) : null}
              <button
                type="button"
                className="title-cta title-cta-ghost"
                onClick={backToExplore}
                data-testid="library-back-to-explore"
              >
                Back to Explore
              </button>
            </div>
          </div>
        ) : null}

        {error && !(ended && endNote) ? (
          <div
            className="live-player-status live-player-status--error"
            data-testid="library-player-error"
          >
            <p>{error}</p>
            <div className="theater-resume-actions">
              <button
                type="button"
                className="title-cta title-cta-primary"
                disabled={startBusy}
                onClick={() => begin({ startOver: false })}
              >
                Try again
              </button>
              {plexHref ? (
                <a
                  className="title-cta title-cta-ghost"
                  href={plexHref}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open in Plex
                </a>
              ) : null}
            </div>
          </div>
        ) : null}
      </TheaterPlayer>
    </div>
  );
}
