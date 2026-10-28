import { useEffect, useRef, useState } from "react";
import TuningInterstitial from "./TuningInterstitial";
import { PREROLL_TAP_COPY, playBumperVideo } from "../../lib/prerollClient.js";

export type PrerollStageProps = {
  src?: string;
  onDone?: (...args: any[]) => void;
  testId?: string;
};

/**
 * Progressive preroll bumper. Plays through with no title and no skip control.
 * Each mount owns its own video — no shared playhead across clients.
 * iOS may pause unmuted autoplay; muted-first then unmute, and the tap overlay
 * always calls play() (it is not a no-op).
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
    setNeedsGesture(true);
    setError(PREROLL_TAP_COPY);
    setStatus("paused");
  }

  function markPlaying() {
    needsGestureRef.current = false;
    setNeedsGesture(false);
    setError("");
    setStatus("playing");
  }

  async function attemptPlay() {
    const video = videoRef.current;
    const result = await playBumperVideo(video);
    if (result === "playing") {
      markPlaying();
      return;
    }
    markGestureNeeded();
  }

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) {
      onDoneRef.current?.();
      return undefined;
    }
    let cancelled = false;
    needsGestureRef.current = false;
    setNeedsGesture(false);
    setStatus("loading");
    setError("");
    video.setAttribute("playsinline", "true");
    video.setAttribute("webkit-playsinline", "true");
    video.src = src;
    video.load();
    playBumperVideo(video).then((result) => {
      if (cancelled) return;
      if (result === "playing") markPlaying();
      else markGestureNeeded();
    });
    return () => {
      cancelled = true;
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
        onWaiting={() => {
          if (needsGestureRef.current) return;
          setStatus("loading");
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
