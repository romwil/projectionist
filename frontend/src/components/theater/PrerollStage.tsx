import { useEffect, useRef, useState } from "react";
import TuningInterstitial from "./TuningInterstitial";
import {
  BUMPER_PLAY_TIMEOUT_MS,
  PREROLL_TAP_COPY,
  bumperPlaySettle,
  bumperReadyPlayGate,
  bumperWatchDecision,
  playBumperVideo,
} from "../../lib/prerollClient.js";

export type PrerollStageProps = {
  src?: string;
  onDone?: (...args: any[]) => void;
  testId?: string;
};

/**
 * Progressive preroll bumper. Plays through with no title and no skip control.
 * Each mount owns its own video — no shared playhead across clients.
 * iOS may pause unmuted autoplay; muted-first then unmute, and the tap overlay
 * always calls play() (it is not a no-op). A hung first frame skips to the show.
 * loadeddata and canplay share onReady; only one play() may be in flight.
 */
export default function PrerollStage({
  src = "",
  onDone,
  testId = "preroll-stage",
}: PrerollStageProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [needsGesture, setNeedsGesture] = useState(false);
  const needsGestureRef = useRef(false);
  const playResultRef = useRef("idle");
  // LivePlayer re-renders about once a second for the OSD clock, and both
  // players pass inline onDone. That identity must not retrigger this effect:
  // cleanup strips `src`, then the effect loads and plays again, which
  // restarts the bumper from 0.
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  function markGestureNeeded() {
    needsGestureRef.current = true;
    playResultRef.current = "ready";
    setNeedsGesture(true);
    setError(PREROLL_TAP_COPY);
    setStatus("paused");
  }

  function markPlaying() {
    needsGestureRef.current = false;
    playResultRef.current = "playing";
    setNeedsGesture(false);
    setError("");
    setStatus("playing");
  }

  async function attemptPlay() {
    const video = videoRef.current;
    const result = await playBumperVideo(video);
    const action = bumperPlaySettle({
      result,
      playResult: playResultRef.current,
      videoPlaying: Boolean(video && !video.paused && !video.ended),
    });
    if (action === "playing") {
      markPlaying();
      return;
    }
    if (action === "skip") {
      onDoneRef.current?.();
      return;
    }
    if (action === "gesture") {
      markGestureNeeded();
    }
  }

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) {
      onDoneRef.current?.();
      return undefined;
    }
    let cancelled = false;
    let playInFlight = false;
    let watchTimer: ReturnType<typeof setTimeout> | null = null;
    needsGestureRef.current = false;
    playResultRef.current = "idle";
    setNeedsGesture(false);
    setStatus("loading");
    setError("");
    video.setAttribute("playsinline", "true");
    video.setAttribute("webkit-playsinline", "true");

    const skip = () => {
      if (cancelled) return;
      cancelled = true;
      onDoneRef.current?.();
    };

    const startedAt = Date.now();
    const tickWatch = () => {
      if (cancelled) return;
      const decision = bumperWatchDecision({
        playResult: playResultRef.current,
        currentTime: video.currentTime,
        error: Boolean(video.error),
        elapsedMs: Date.now() - startedAt,
      });
      if (decision === "skip") {
        skip();
        return;
      }
      watchTimer = window.setTimeout(tickWatch, 400);
    };

    const startWatch = () => {
      if (watchTimer != null) return;
      watchTimer = window.setTimeout(tickWatch, 400);
    };

    const onReady = () => {
      if (
        bumperReadyPlayGate({
          cancelled,
          playResult: playResultRef.current,
          playInFlight,
        }) !== "start"
      ) {
        return;
      }
      playInFlight = true;
      playBumperVideo(video).then((result) => {
        const action = bumperPlaySettle({
          cancelled,
          result,
          playResult: playResultRef.current,
          videoPlaying: Boolean(video && !video.paused && !video.ended),
        });
        if (action === "playing") {
          markPlaying();
          startWatch();
          return;
        }
        if (action === "skip") {
          skip();
          return;
        }
        if (action === "gesture") {
          markGestureNeeded();
          startWatch();
        }
      });
    };

    video.addEventListener("loadeddata", onReady, { once: true });
    video.addEventListener("canplay", onReady, { once: true });
    video.src = src;
    video.load();
    const attachTimer = window.setTimeout(() => {
      if (cancelled) return;
      if (playResultRef.current === "idle" && (video.readyState || 0) < 2) skip();
    }, BUMPER_PLAY_TIMEOUT_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(attachTimer);
      if (watchTimer != null) window.clearTimeout(watchTimer);
      video.removeAttribute("src");
      video.load();
    };
  }, [src]);

  return (
    <div
      className="preroll-stage"
      data-testid={testId}
      data-status={status}
      data-needs-gesture={needsGesture ? "1" : "0"}
    >
      <video
        ref={videoRef}
        className="preroll-stage-video"
        playsInline
        autoPlay
        controls={false}
        data-testid={`${testId}-video`}
        onPlaying={markPlaying}
        onTimeUpdate={() => {
          const video = videoRef.current;
          if (!video || video.currentTime < 0.2) return;
          if (status !== "playing") markPlaying();
        }}
        onEnded={() => onDoneRef.current?.()}
        onError={() => {
          setError("Bumper unavailable — continuing to the show.");
          window.setTimeout(() => onDoneRef.current?.(), 400);
        }}
      />
      <TuningInterstitial active={status === "loading" && !needsGesture} testId={`${testId}-tuning`} />
      {needsGesture ? (
        <button
          type="button"
          className="preroll-stage-tap"
          data-testid={`${testId}-tap`}
          data-theater-chrome="true"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            attemptPlay();
          }}
        >
          <span className="preroll-stage-error">{error || PREROLL_TAP_COPY}</span>
        </button>
      ) : error ? (
        <p className="preroll-stage-error" data-theater-chrome="true">{error}</p>
      ) : null}
    </div>
  );
}
