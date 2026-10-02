import { useEffect, useState } from "react";
import { activeCueText } from "../../lib/subtitleCues.js";

/**
 * Renders the active cue over the stage. `getTimeSec` returns media seconds
 * (video.currentTime for Play, program elapsed for Live); `delaySec` shifts cues.
 */
export default function SubtitleOverlay({ cues, getTimeSec, delaySec = 0, testId = "subtitle-overlay" }) {
  const [text, setText] = useState("");

  useEffect(() => {
    if (!cues?.length) return undefined;
    const tick = () => {
      const t = getTimeSec?.();
      setText(Number.isFinite(t) ? activeCueText(cues, t - delaySec) : "");
    };
    tick();
    const id = setInterval(tick, 200);
    return () => clearInterval(id);
  }, [cues, getTimeSec, delaySec]);

  if (!cues?.length || !text) return null;
  return (
    <div className="subtitle-overlay" data-testid={testId} aria-live="off">
      <span className="subtitle-overlay-text">{text}</span>
    </div>
  );
}
