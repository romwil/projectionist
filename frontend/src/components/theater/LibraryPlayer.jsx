import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  progressLibraryPlayback,
  seekLibraryPlayback,
  startLibraryPlayback,
  stopLibraryPlayback,
} from "../../api/client";
import { isPhonePlayViewport } from "../../lib/chatLayout.js";
import {
  SKIP_SECONDS,
  bufferedRanges,
  clampTime,
  formatClockMs,
  libraryWatchPath,
  libraryWatchPopoutPath,
  shouldResumeFromOffset,
  shouldSendProgress,
  skipDeltaForZone,
} from "../../lib/theaterPlayer.js";
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
  const [bufferedEndS, setBufferedEndS] = useState(0);
  const [phone, setPhone] = useState(() => isPhonePlayViewport());
  const [pipSupported, setPipSupported] = useState(false);
  const [startBusy, setStartBusy] = useState(false);

  const key = String(ratingKey || "").trim();

  useEffect(() => {
    const onResize = () => setPhone(isPhonePlayViewport());
    window.addEventListener("resize", onResize);
    setPipSupported(Boolean(document.pictureInPictureEnabled));
    return () => window.removeEventListener("resize", onResize);
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

  const disarmStream = useCallback(() => {
    sessionRef.current = null;
    // Keep poster/title for the shell, but drop the dead stream URL so TheaterPlayer
    // detaches HLS and Play can begin() again instead of calling play() on nothing.
    setSession((prev) => (prev ? { ...prev, stream_url: "", session_id: "" } : prev));
    setStatus("paused");
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
    function onHide() {
      if (document.visibilityState === "hidden") {
        stopSession().finally(() => disarmStream());
      }
    }
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onHide);
    };
  }, [stopSession, disarmStream]);

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

  async function applySeekRestart(offsetMs) {
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

  function skipBy(deltaSeconds, { preferLocal = true } = {}) {
    const video = videoRef.current;
    const duration = video?.duration || durationMs / 1000;
    const current = video?.currentTime || nowMs / 1000;
    const target = clampTime(current + deltaSeconds, duration);
    const buffered = bufferedRanges(video);
    const inBuffer = buffered.some((range) => target >= range.start && target <= range.end);
    if (preferLocal && video && (Math.abs(deltaSeconds) <= SKIP_SECONDS || inBuffer)) {
      applyLocalSkip(deltaSeconds);
      return;
    }
    applySeekRestart(Math.round(target * 1000));
    const label = deltaSeconds < 0 ? `−${SKIP_SECONDS}s` : `+${SKIP_SECONDS}s`;
    setSkipChip(label);
    window.setTimeout(() => setSkipChip(""), 900);
  }

  async function togglePlayback() {
    if (status === "loading" || status === "error" || resumeOpen) return;
    const video = videoRef.current;
    // Tab-hide stopSession clears the server session + stream_url. Play must
    // re-arm via begin() instead of no-op play() on an empty <video>.
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
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    } else {
      root?.requestFullscreen?.().catch(() => {});
    }
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
    const key = event.key;
    if (key === " " || key === "k" || key === "K") {
      event.preventDefault();
      togglePlayback();
    } else if (key === "j" || key === "J" || key === "ArrowLeft") {
      event.preventDefault();
      skipBy(-SKIP_SECONDS);
    } else if (key === "l" || key === "L" || key === "ArrowRight") {
      event.preventDefault();
      skipBy(SKIP_SECONDS);
    } else if (key === "m" || key === "M") {
      event.preventDefault();
      if (video) video.muted = !video.muted;
    } else if (key === "c" || key === "C") {
      event.preventDefault();
      setCcOpen((open) => !open);
      setMoreOpen(false);
    } else if (key === "Escape") {
      event.preventDefault();
      if (moreOpen) {
        setMoreOpen(false);
        return;
      }
      if (ccOpen) {
        setCcOpen(false);
        return;
      }
      if (document.fullscreenElement) {
        document.exitFullscreen?.().catch(() => {});
        return;
      }
      leaveWatch();
    } else if (key === "f" || key === "F") {
      fs?.();
    }
  }

  function onScrub(event) {
    const duration = durationMs || Math.round((videoRef.current?.duration || 0) * 1000);
    if (!duration) return;
    const value = Number(event.target.value);
    const offset = Math.round((value / 1000) * duration);
    applySeekRestart(offset);
  }

  const plexHref = session?.plex_watch_url || "";
  const next = session?.next_episode;
  const showOsd = !resumeOpen && !ended;
  const playing = status === "playing";
  const showCenterPlay =
    showOsd && !playing && !error && status !== "loading" && Boolean(session);
  const durationS = durationMs / 1000 || 0;
  const bufferedPct = durationS ? Math.round((bufferedEndS / durationS) * 100) : 0;
  const playheadPct = durationMs ? Math.round((nowMs / durationMs) * 1000) : 0;
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
            max={1000}
            value={Math.max(0, Math.min(1000, playheadPct))}
            aria-label="Seek"
            onChange={onScrub}
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
    <div className={`library-watch ${phone ? "library-watch--phone" : ""} ${className}`.trim()}>
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
          setNowMs(Math.round((video.currentTime || 0) * 1000));
          if (video.duration) setDurationMs(Math.round(video.duration * 1000));
          const ranges = bufferedRanges(video);
          setBufferedEndS(ranges[ranges.length - 1]?.end || 0);
          sendProgress("playing", video);
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
