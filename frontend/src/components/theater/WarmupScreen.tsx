import { useEffect, useRef, useState } from "react";
import { getWarmupLines } from "../../api/client.js";
import {
  LINE_HOLD_MS,
  artFace,
  choicesDue,
  honestStatus,
  jokeForHumor,
  nextWarmupLine,
  type WarmupHumor,
  type WarmupLines,
} from "../../lib/warmupScreen.js";

export type WarmupScreenProps = {
  title?: string;
  year?: string;
  runtime?: string;
  room?: string;
  posterUrl?: string;
  backdropUrl?: string;
  step?: string;
  reason?: string;
  lines?: WarmupLines | null;
  humor?: WarmupHumor;
  elapsedMs?: number;
  hasPicture?: boolean;
  choicesHeld?: boolean;
  onKeepWaiting?: () => void;
  onTryAgain?: () => void;
  onBack?: () => void;
};

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(query.matches);
    apply();
    query.addEventListener?.("change", apply);
    return () => query.removeEventListener?.("change", apply);
  }, []);
  return reduced;
}

/**
 * The wait before the first frame. Joke lines are decorative. The status is
 * the only thing a screen reader hears.
 */
export default function WarmupScreen({
  title = "",
  year = "",
  runtime = "",
  room = "",
  posterUrl = "",
  backdropUrl = "",
  step = "",
  reason = "",
  lines = null,
  humor = "on",
  elapsedMs = 0,
  hasPicture = false,
  choicesHeld = false,
  onKeepWaiting,
  onTryAgain,
  onBack,
}: WarmupScreenProps) {
  const reduced = useReducedMotion();
  const [fetched, setFetched] = useState<WarmupLines | null>(null);
  const lineDoc = lines || fetched;
  const choices = !choicesHeld && choicesDue({ elapsedMs, hasPicture });
  const usedRef = useRef(new Set<string>());
  const [line, setLine] = useState("");
  const face = artFace(elapsedMs, reduced);
  useEffect(() => {
    if (lines) return undefined;
    let cancelled = false;
    getWarmupLines()
      .then((doc) => {
        if (!cancelled) setFetched(doc as WarmupLines);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [lines]);

  const joke = jokeForHumor(humor, line, choices);
  const status = honestStatus(step, elapsedMs);
  const meta = [year, runtime].filter(Boolean).join(" · ");
  const backdrop = backdropUrl || posterUrl;
  const poster = posterUrl || backdropUrl;

  useEffect(() => {
    if (choices || humor !== "on" || line) return undefined;
    const text = nextWarmupLine(lineDoc, step, usedRef.current);
    if (!text) return undefined;
    usedRef.current.add(text);
    setLine(text);
    return undefined;
  }, [choices, humor, line, lineDoc, step]);

  useEffect(() => {
    if (choices || humor !== "on" || !line) return undefined;
    const timer = window.setTimeout(() => setLine(""), LINE_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [choices, humor, line]);

  useEffect(() => {
    if (!choices) return undefined;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onBack?.();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choices, onBack]);

  return (
    <section
      className={`warmup-screen${reduced ? " warmup-screen--still" : ""}`}
      data-testid="warmup-screen"
      data-step={step || "starting"}
      data-choices={choices ? "true" : "false"}
      data-humor={humor}
    >
      <div className="warmup-art" aria-hidden="true">
        {backdrop ? (
          <img
            className={`warmup-art-layer${face === "backdrop" ? " is-on" : ""}`}
            src={backdrop}
            alt=""
          />
        ) : null}
        {poster ? (
          <img
            className={`warmup-art-layer warmup-art-layer--poster${face === "poster" ? " is-on" : ""}`}
            src={poster}
            alt=""
          />
        ) : null}
        <div className="warmup-scrim" />
        {humor !== "off" && !reduced ? <div className="warmup-beam" /> : null}
      </div>
      <div className="warmup-copy" aria-hidden="true">
        <p className="warmup-kicker">{room ? `Now starting · ${room}` : "Now starting"}</p>
        {title ? <h1 className="warmup-title">{title}</h1> : null}
        {meta ? <p className="warmup-meta">{meta}</p> : null}
        {joke ? (
          <p className="warmup-line" data-testid="warmup-line">
            {joke}
          </p>
        ) : null}
        {humor === "off" ? <p className="warmup-spinner" /> : null}
        {!choices ? <p className="warmup-cancel">Press Back to cancel</p> : null}
      </div>
      <p className="warmup-status" role="status" aria-live="polite" data-testid="warmup-status">
        {status}
      </p>
      {choices ? (
        <div className="warmup-choices" data-testid="warmup-choices">
          <p className="warmup-reason">{reason || status}</p>
          <div className="warmup-choice-row">
            <button type="button" onClick={onKeepWaiting}>Keep waiting</button>
            <button type="button" onClick={onTryAgain}>Try again</button>
            <button type="button" onClick={onBack}>Back</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
