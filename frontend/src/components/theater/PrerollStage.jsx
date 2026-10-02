import { useEffect, useRef, useState } from "react";
import TuningInterstitial from "./TuningInterstitial.jsx";

/**
 * Progressive preroll bumper. Plays through with no title and no skip control.
 * Each mount owns its own video — no shared playhead across clients.
 */
export default function PrerollStage({
  src = "",
  onDone,
  testId = "preroll-stage",
}) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  // LivePlayer re-renders about once a second for the OSD clock, and both
  // players pass inline onDone. That identity must not retrigger this effect:
  // cleanup strips `src`, then the effect loads and plays again, which
  // restarts the bumper from 0.
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
        setError("Tap the picture to start the bumper.");
        setStatus("paused");
      });
    }
    return () => {
      video.removeAttribute("src");
      video.load();
    };
  }, [src]);

  return (
    <div
      className="preroll-stage"
      data-testid={testId}
      data-status={status}
      onClick={() => {
        if (status !== "paused") return;
        const video = videoRef.current;
        video?.play?.().then(() => {
          setError("");
          setStatus("playing");
        }).catch(() => {});
      }}
    >
      <video
        ref={videoRef}
        className="preroll-stage-video"
        playsInline
        autoPlay
        controls={false}
        data-testid={`${testId}-video`}
        onPlaying={() => setStatus("playing")}
        onWaiting={() => setStatus("loading")}
        onEnded={() => onDoneRef.current?.()}
        onError={() => {
          setError("Bumper unavailable — continuing to the show.");
          window.setTimeout(() => onDoneRef.current?.(), 400);
        }}
      />
      <TuningInterstitial active={status === "loading"} testId={`${testId}-tuning`} />
      {error ? (
        <p className="preroll-stage-error" data-theater-chrome="true">{error}</p>
      ) : null}
    </div>
  );
}
