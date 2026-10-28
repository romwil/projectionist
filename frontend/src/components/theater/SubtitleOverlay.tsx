import { useEffect, useState } from "react";
import { activeCueText, subtitleLookupTimeSec } from "../../lib/subtitleCues.js";

export type SubtitleCue = {
  start: number;
  end: number;
  text: string;
};

export type SubtitleOverlayProps = {
  cues?: SubtitleCue[] | null;
  getTimeSec?: () => number | null | undefined;
  delaySec?: number;
  testId?: string;
};

// JS helper infers only defaulted keys; lookup uses currentTimeSec + delaySec.
const lookupTimeSec = subtitleLookupTimeSec as (opts?: {
  currentTimeSec?: number | null;
  delaySec?: number;
}) => number;

/**
 * Renders the active cue over the stage. `getTimeSec` returns media seconds
 * already corrected for seek origin (Play) or program elapsed (Live).
 * `delaySec` shifts cues via {@link subtitleLookupTimeSec}.
 */
export default function SubtitleOverlay({
  cues,
  getTimeSec,
  delaySec = 0,
  testId = "subtitle-overlay",
}: SubtitleOverlayProps) {
  const [text, setText] = useState("");

  useEffect(() => {
    if (!cues?.length) return undefined;
    const tick = () => {
      const t = getTimeSec?.();
      const lookup = lookupTimeSec({ currentTimeSec: t, delaySec });
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
