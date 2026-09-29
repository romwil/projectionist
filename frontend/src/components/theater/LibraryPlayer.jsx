import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  progressLibraryPlayback,
  seekLibraryPlayback,
  startLibraryPlayback,
  stopLibraryPlayback,
} from "../../api/client";
import { isCompactPlayViewport, isPhonePlayViewport } from "../../lib/chatLayout.js";
import {
  SCRUB_MAX,
  SEEK_RESTART_DEBOUNCE_MS,
  SKIP_SECONDS,
  bufferedRanges,
  canLocalSeekTo,
  canResumeAttachedStream,
  clampTime,
  formatClockMs,
  isDocumentFullscreen,
  libraryWatchPath,
  libraryWatchPopoutPath,
  msFromScrubPct,
  notePlayingBeforeHide,
  scrubPctFromMs,
  shouldAutoResumePlayback,
  shouldPauseOnVisibilityHide,
  shouldResumeFromOffset,
  shouldSendProgress,
  skipDeltaForZone,
  theaterKeyAction,
  toggleTheaterFullscreen,
} from "../../lib/theaterPlayer.js";
import {
  UI_PREFS_CHANGED_EVENT,
  loadPauseWhenBackgrounded,
} from "../../lib/uiPrefs.js";
import { plexPlayRatingKey } from "../../lib/titleLinks.js";
import TheaterPlayer from "./TheaterPlayer.jsx";

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

export default function LibraryPlayer({
  ratingKey,
  popout = false,
  className = "",
}) {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const sessionRef = useRef(null);
  const lastProgressAtRef = useRef(null);
  const startingRef = useRef(false);
  const wasPlayingBeforeHideRef = useRef(false);
  const pauseWhenBackgroundedRef = useRef(loadPauseWhenBackgrounded());
  /** True while the user is dragging the scrubber — blocks timeupdate from stealing the thumb. */
  const scrubbingRef = useRef(false);
  /** Collapses rapid scrub-end session restarts into one seek. */
  const seekRestartTimerRef = useRef(null);
  const seekRestartPendingMsRef = useRef(null);
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [resumeOpen, setResumeOpen] = useState(false);
  const [ended, setEnded] = useState(false);
  const [skipChip, setSkipChip] = useState("");
  const [ccOpen, setCcOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [nowMs, setNowMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  /** Non-null while dragging/keyboard-scrubbing — drives the range value instead of playhead. */
  const [scrubPct, setScrubPct] = useState(null);
  const [bufferedEndS, setBufferedEndS] = useState(0);
  const [phone, setPhone] = useState(() => isPhonePlayViewport());
  const [compact, setCompact] = useState(() => isCompactPlayViewport());
  const [pipSupported, setPipSupported] = useState(false);
  const [startBusy, setStartBusy] = useState(false);

  const key = String(ratingKey || "").trim();

  useEffect(() => {
    const syncViewport = () => {
      setPhone(isPhonePlayViewport());
      setCompact(isCompactPlayViewport());
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
    };
  }, []);

  const stopSession = useCallback(async (extra = {}) => {
    const current = sessionRef.current;
    if (!current?.session_id) return;
    const video = videoRef.current;
    try {
      await stopLibraryPlayback(current.session_id, {
        time_ms: extra.time_ms ?? Math.round((video?.currentTime || 0) * 1000),
        duration_ms: extra.duration_ms ?? Math.round((video?.duration || 0) * 1000),
      });
    } catch {
      // Best-effort — unmount / hide still tears down local state.
    }
    sessionRef.current = null;
  }, []);

  const handlePlayerStatus = useCallback((next) => {
    setStatus(next);
    if (next === "error") {
      setError((prev) => prev || "Playback stalled. Try Resume, refresh, or Open in Plex.");
    } else if (next === "playing" || next === "ready") {
      setError("");
    }
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
          } catch {
            // replace the session below
          }
          sessionRef.current = null;
        }
        const payload = await startLibraryPlayback(key, { startOver });
        sessionRef.current = payload;
        setSession(payload);
        setDurationMs(Number(payload.duration_ms) || 0);
        setNowMs(startOver ? 0 : Number(payload.view_offset_ms) || 0);
        setResumeOpen(false);
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
        setSession(payload);
        setDurationMs(Number(payload.duration_ms) || 0);
        setNowMs(Number(payload.view_offset_ms) || 0);
        if (shouldResumeFromOffset(payload.view_offset_ms) && payload.can_resume) {
          setResumeOpen(true);
          setStatus("paused");
        } else {
          setStatus("ready");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || "This title couldn’t start in Projectionist.");
          setStatus("error");
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
        if (shouldPauseOnVisibilityHide({ pauseWhenBackgrounded: pausePref, visibilityState: state })) {
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

    function onPageHide() {
      // Real navigation / close — free the transcoder. Do not disarm on mere hide.
      stopSession();
    }

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
    };
    // begin / sendProgress / session are stable enough via refs for this lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- visibility controller
  }, [stopSession]);

  async function sendProgress(state, video) {
    const current = sessionRef.current;
    if (!current?.session_id) return;
    const now = Date.now();
    if (state !== "stopped" && !shouldSendProgress(lastProgressAtRef.current, now)) return;
    lastProgressAtRef.current = now;
    try {
      await progressLibraryPlayback(current.session_id, {
        state,
        time_ms: Math.round((video?.currentTime || 0) * 1000),
        duration_ms: Math.round((video?.duration || durationMs / 1000 || 0) * 1000),
      });
    } catch {
      // Progress is best-effort.
    }
  }

  function applyLocalSkip(deltaSeconds) {
    const video = videoRef.current;
    if (!video) return;
    const next = clampTime((video.currentTime || 0) + deltaSeconds, video.duration || durationMs / 1000);
    try {
      video.currentTime = next;
    } catch {
      // Some browsers reject currentTime before metadata.
    }
    setNowMs(next * 1000);
    const label = deltaSeconds < 0 ? `−${SKIP_SECONDS}s` : `+${SKIP_SECONDS}s`;
    setSkipChip(label);
    window.setTimeout(() => setSkipChip(""), 900);
  }

  async function applySeekRestartNow(offsetMs) {
    const current = sessionRef.current;
    if (!current?.session_id) return;
    try {
      const next = await seekLibraryPlayback(current.session_id, offsetMs);
      sessionRef.current = next;
      setSession(next);
      setNowMs(offsetMs);
    } catch (err) {
      setError(err?.message || "Couldn’t jump in this title.");
    }
  }

  /** Debounce Plex session-restart seeks from scrub / skip spam. */
  function applySeekRestart(offsetMs) {
    seekRestartPendingMsRef.current = offsetMs;
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

  /** Local currentTime when buffered; otherwise Plex session restart at offset. */
  function seekToOffsetMs(offsetMs) {
    const video = videoRef.current;
    const durationS = video?.duration || durationMs / 1000;
    const target = clampTime(offsetMs / 1000, durationS);
    const targetMs = Math.round(target * 1000);
    if (video && canLocalSeekTo(video, target)) {
      if (seekRestartTimerRef.current) {
        window.clearTimeout(seekRestartTimerRef.current);
        seekRestartTimerRef.current = null;
        seekRestartPendingMsRef.current = null;
      }
      try {
        video.currentTime = target;
      } catch {
        // Some browsers reject currentTime before metadata.
      }
      setNowMs(targetMs);
      return;
    }
    applySeekRestart(targetMs);
  }

  function skipBy(deltaSeconds, { preferLocal = true } = {}) {
    const video = videoRef.current;
    const duration = video?.duration || durationMs / 1000;
    const current = video?.currentTime || nowMs / 1000;
    const target = clampTime(current + deltaSeconds, duration);
    const inBuffer = canLocalSeekTo(video, target);
    if (preferLocal && video && (Math.abs(deltaSeconds) <= SKIP_SECONDS || inBuffer)) {
      applyLocalSkip(deltaSeconds);
      return;
    }
    applySeekRestart(Math.round(target * 1000));
    const label = deltaSeconds < 0 ? `−${SKIP_SECONDS}s` : `+${SKIP_SECONDS}s`;
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

  function beginScrub(event) {
    scrubbingRef.current = true;
    previewScrub(Number(event.target.value));
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {
      // Pointer may already be released; pointerup/cancel still end the scrub.
    }
  }

  function onScrubInput(event) {
    const pct = Number(event.target.value);
    previewScrub(pct);
    // Keyboard / assistive scrub: no pointerdown, so commit each step.
    if (!scrubbingRef.current) {
      const duration = scrubDurationMs();
      if (!duration) return;
      seekToOffsetMs(msFromScrubPct(pct, duration));
      setScrubPct(null);
    }
  }

  function endScrub(event) {
    if (!scrubbingRef.current) return;
    scrubbingRef.current = false;
    const duration = scrubDurationMs();
    const pct = Number(event.target.value);
    setScrubPct(null);
    if (!duration) return;
    seekToOffsetMs(msFromScrubPct(pct, duration));
  }

  async function togglePlayback() {
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
    navigate(-1);
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
    toggleTheaterFullscreen(root);
  }

  function handleStageActivate(_event, _zone) {
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
    const action = theaterKeyAction(event.key);
    if (!action) return;
    if (action === "toggle") {
      event.preventDefault();
      togglePlayback();
    } else if (action === "skipBack") {
      event.preventDefault();
      skipBy(-SKIP_SECONDS);
    } else if (action === "skipForward") {
      event.preventDefault();
      skipBy(SKIP_SECONDS);
    } else if (action === "mute") {
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
        toggleTheaterFullscreen(root);
        return;
      }
      {
        const root = document.querySelector("[data-testid='library-player']");
        if (root?.classList.contains("theater-player--immersive")) {
          toggleTheaterFullscreen(root);
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
  const showOsd = !resumeOpen && !ended;
  const playing = status === "playing";
  const showCenterPlay =
    showOsd && !playing && !error && status !== "loading" && Boolean(session);
  const durationS = durationMs / 1000 || 0;
  const bufferedPct = durationS ? Math.round((bufferedEndS / durationS) * 100) : 0;
  const playheadPct = scrubPctFromMs(nowMs, durationMs);
  const sliderPct = scrubPct != null ? scrubPct : playheadPct;
  const headline = displayHeadline(session);
  const metaLine = displayMeta(session);
  const forceOsd = moreOpen || ccOpen;

  const osd = showOsd ? (
    <div className="theater-osd-inner" data-testid="library-osd-inner">
      <div className="theater-osd-meta">
        {popout ? <p className="theater-osd-kicker">Pop-out</p> : null}
        <h2 className="theater-osd-title">{headline}</h2>
        {metaLine ? <p className="theater-osd-episode">{metaLine}</p> : null}
      </div>

      <div className="theater-scrubber-row" data-testid="library-scrubber-row">
        <span className="theater-clock">{formatClockMs(nowMs)}</span>
        <label className="theater-scrubber" data-theater-chrome="true">
          <span className="visually-hidden">Seek</span>
          <span
            className="theater-scrubber-buffered"
            style={{ width: `${Math.max(0, Math.min(100, bufferedPct))}%` }}
          />
          <input
            type="range"
            min={0}
            max={SCRUB_MAX}
            step={1}
            value={Math.max(0, Math.min(SCRUB_MAX, sliderPct))}
            aria-label="Seek"
            aria-valuetext={formatClockMs(nowMs)}
            onPointerDown={beginScrub}
            onPointerUp={endScrub}
            onPointerCancel={endScrub}
            onChange={onScrubInput}
          />
        </label>
        <span className="theater-clock">{durationMs ? formatClockMs(durationMs) : "–:––"}</span>
      </div>

      <div className="theater-osd-transport" data-testid="library-osd-transport">
        <button
          type="button"
          className="theater-osd-skip"
          onClick={() => skipBy(-SKIP_SECONDS)}
          aria-label={`Skip back ${SKIP_SECONDS} seconds`}
          data-testid="library-skip-back"
        >
          −{SKIP_SECONDS}
        </button>
        <button
          type="button"
          className="theater-osd-play"
          onClick={togglePlayback}
          aria-label={playing ? "Pause" : "Play"}
          data-testid="library-play-toggle"
        >
          <span className="theater-osd-play-glyph" aria-hidden="true">
            {playing ? "❚❚" : "▶"}
          </span>
          <span className="theater-osd-play-label">{playing ? "Pause" : "Play"}</span>
        </button>
        <button
          type="button"
          className="theater-osd-skip"
          onClick={() => skipBy(SKIP_SECONDS)}
          aria-label={`Skip forward ${SKIP_SECONDS} seconds`}
          data-testid="library-skip-forward"
        >
          +{SKIP_SECONDS}
        </button>

        <span className="theater-osd-spacer" aria-hidden="true" />

        <button
          type="button"
          className={`theater-osd-secondary${ccOpen ? " is-active" : ""}`}
          onClick={() => {
            setCcOpen((open) => !open);
            setMoreOpen(false);
          }}
          aria-expanded={ccOpen}
          data-testid="library-cc"
        >
          CC
        </button>
        <button
          type="button"
          className="theater-osd-secondary"
          onClick={toggleFullscreen}
          data-testid="library-fullscreen"
        >
          Fullscreen
        </button>
        <div className="theater-osd-more-wrap" data-theater-chrome="true">
          <button
            type="button"
            className={`theater-osd-secondary${moreOpen ? " is-active" : ""}`}
            onClick={() => {
              setMoreOpen((open) => !open);
              setCcOpen(false);
            }}
            aria-expanded={moreOpen}
            aria-haspopup="menu"
            data-testid="library-osd-more"
          >
            More
          </button>
          {moreOpen ? (
            <div className="theater-osd-menu" role="menu" data-testid="library-osd-menu">
              {pipSupported ? (
                <button type="button" role="menuitem" onClick={() => { enterPiP(); setMoreOpen(false); }}>
                  Picture in Picture
                </button>
              ) : null}
              {!phone && !popout ? (
                <button type="button" role="menuitem" onClick={() => { openPopout(); setMoreOpen(false); }}>
                  Pop-out
                </button>
              ) : null}
              {plexHref ? (
                <a
                  role="menuitem"
                  href={plexHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMoreOpen(false)}
                >
                  Open in Plex
                </a>
              ) : null}
              <button type="button" role="menuitem" onClick={leaveWatch} data-testid="library-osd-back">
                Back
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {ccOpen ? (
        <div className="theater-cc-note" data-theater-chrome="true" data-testid="library-cc-note">
          <p>Captions follow the Plex-selected track when the stream carries them.</p>
        </div>
      ) : null}
    </div>
  ) : null;

  return (
    <div
      className={`library-watch ${phone ? "library-watch--phone" : ""} ${compact ? "library-watch--compact" : ""} ${className}`.trim()}
      data-play-phone={phone ? "true" : "false"}
      data-play-compact={compact ? "true" : "false"}
    >
      <TheaterPlayer
        src={resumeOpen || ended || !session?.stream_url ? "" : session.stream_url}
        poster={session?.poster_url || ""}
        className="library-player"
        testId="library-player"
        videoTestId="library-player-video"
        loading={status === "loading" && !resumeOpen}
        loadingCopy="warming the reel"
        error=""
        osd={osd}
        osdVisible={forceOsd ? true : undefined}
        onStatus={handlePlayerStatus}
        onVideoRef={handleVideoRef}
        onHlsRef={handleHlsRef}
        onTimeUpdate={(video) => {
          if (!scrubbingRef.current) {
            setNowMs(Math.round((video.currentTime || 0) * 1000));
          }
          if (video.duration) setDurationMs(Math.round(video.duration * 1000));
          const ranges = bufferedRanges(video);
          setBufferedEndS(ranges[ranges.length - 1]?.end || 0);
          if (!scrubbingRef.current) sendProgress("playing", video);
        }}
        onEnded={() => {
          setEnded(true);
          setMoreOpen(false);
          sendProgress("stopped", videoRef.current);
        }}
        onStageActivate={handleStageActivate}
        onStageDoubleActivate={handleStageDoubleActivate}
        onKeyDown={handleKeyDown}
      >
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
          <div className="theater-end-card" data-testid="library-end-card">
            <p className="theater-end-kicker">That’s the reel</p>
            <div className="theater-resume-actions">
              {next?.rating_key ? (
                <Link
                  className="title-cta title-cta-primary"
                  to={libraryWatchPath(plexPlayRatingKey(next) || next.rating_key)}
                >
                  Next episode
                </Link>
              ) : (
                <button type="button" className="title-cta title-cta-primary" onClick={leaveWatch}>
                  Back to title
                </button>
              )}
            </div>
          </div>
        ) : null}

        {error ? (
          <div className="live-player-status live-player-status--error" data-testid="library-player-error">
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
                <a className="title-cta title-cta-ghost" href={plexHref} target="_blank" rel="noopener noreferrer">
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
