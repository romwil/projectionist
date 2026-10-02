import { useEffect, useRef, useState } from "react";
import TuningInterstitial from "./TuningInterstitial.jsx";

/**
 * Progressive preroll bumper staged before movie / Live start.
 * Each mount fetches its own bumper — no shared playhead across clients.
 */
export default function PrerollStage({
  src = "",
  title = "Preroll",
  onDone,
  onSkip,
  testId = "preroll-stage",
}) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  // LivePlayer re-renders about once a second for the OSD clock, and both
  // players pass inline onDone/onSkip. Those identities must not retrigger
  // this effect: cleanup strips `src`, then the effect loads and plays again,
  // which restarts the bumper from 0. onSkip is click-only (not an effect dep).
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) {
      onDoneRef.current?.();
      return undefined;
    }
    setStatus("loading");
    setError("");
    video.src = src;
    video.load();
    const play = video.play?.();
    if (play && typeof play.then === "function") {
      play.then(() => setStatus("playing")).catch(() => {
        setError("Preroll couldn’t autoplay — tap skip or wait.");
        setStatus("paused");
      });
    }
    return () => {
      video.removeAttribute("src");
      video.load();
    };
  }, [src]);

  return (
    <div className="preroll-stage" data-testid={testId} data-status={status}>
      <video
        ref={videoRef}
        className="preroll-stage-video"
        playsInline
        autoPlay
        controls={false}
        data-testid={`${testId}-video`}
        onPlaying={() => setStatus("playing")}
        onWaiting={() => setStatus("loading")}
        onEnded={() => onDone?.()}
        onError={() => {
          setError("Preroll skipped — jumping to the show.");
          window.setTimeout(() => onDone?.(), 400);
        }}
      />
      <TuningInterstitial active={status === "loading"} testId={`${testId}-tuning`} />
      <div className="preroll-stage-chrome" data-theater-chrome="true">
        <p className="preroll-stage-kicker">Coming up</p>
        <p className="preroll-stage-title">{title}</p>
        {error ? <p className="preroll-stage-error muted">{error}</p> : null}
        <button
          type="button"
          className="preroll-stage-skip"
          data-testid={`${testId}-skip`}
          onClick={() => (onSkip || onDone)?.()}
        >
          Skip bumper
        </button>
      </div>
    </div>
  );
}
