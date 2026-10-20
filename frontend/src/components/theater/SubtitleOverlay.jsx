import { useEffect, useState } from "react";
import { activeCueText, subtitleLookupTimeSec } from "../../lib/subtitleCues.js";

/**
 * Renders the active cue over the stage. `getTimeSec` returns media seconds
 * already corrected for seek origin (Play) or program elapsed (Live).
 * `delaySec` shifts cues via {@link subtitleLookupTimeSec}.
 */
export default function SubtitleOverlay({ cues, getTimeSec, delaySec = 0, testId = "subtitle-overlay" }) {
  const [text, setText] = useState("");

  useEffect(() => {
    if (!cues?.length) return undefined;
    const tick = () => {
      const t = getTimeSec?.();
      const lookup = subtitleLookupTimeSec({ currentTimeSec: t, delaySec });
      setText(Number.isFinite(lookup) ? activeCueText(cues, lookup) : "");
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
