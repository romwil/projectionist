import { useEffect, useRef, useState } from "react";
import { pickTuningPhrase } from "../../lib/tuningCopy.js";

/**
 * Fuzzy CRT static + wry tuning copy while Play seeks or Live tunes.
 * Crossfade off when the parent sets active=false (playback actually started).
 */
export default function TuningInterstitial({
  active = false,
  phrase: phraseProp,
  testId = "tuning-interstitial",
  className = "",
}) {
  const canvasRef = useRef(null);
  const rafRef = useRef(0);
  const [phrase, setPhrase] = useState("");
  const [visible, setVisible] = useState(false);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    if (active) {
      setFading(false);
      setVisible(true);
      setPhrase(phraseProp || pickTuningPhrase({ exclude: phrase }));
      return undefined;
    }
    if (!visible) return undefined;
    setFading(true);
    const t = window.setTimeout(() => {
      setVisible(false);
      setFading(false);
    }, 420);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- lock phrase for this episode
  }, [active, phraseProp]);

  useEffect(() => {
    if (!visible) return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return undefined;

    let alive = true;
    const paint = () => {
      if (!alive) return;
      const w = canvas.width;
      const h = canvas.height;
      const image = ctx.createImageData(w, h);
      const data = image.data;
      for (let i = 0; i < data.length; i += 4) {
        const v = (Math.random() * 255) | 0;
        data[i] = v;
        data[i + 1] = v;
        data[i + 2] = v;
        data[i + 3] = 255;
      }
      ctx.putImageData(image, 0, 0);
      // Soft scanline wash — CRT, not neon sludge.
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      for (let y = 0; y < h; y += 3) {
        ctx.fillRect(0, y, w, 1);
      }
      rafRef.current = window.requestAnimationFrame(paint);
    };

    const syncSize = () => {
      const parent = canvas.parentElement;
      const rect = parent?.getBoundingClientRect();
      const cssW = Math.max(160, Math.floor(rect?.width || 480));
      const cssH = Math.max(90, Math.floor(rect?.height || 270));
      // Keep pixel budget modest for phones.
      const scale = Math.min(1, 480 / cssW);
      canvas.width = Math.max(80, Math.floor(cssW * scale));
      canvas.height = Math.max(45, Math.floor(cssH * scale));
    };
    syncSize();
    paint();
    window.addEventListener("resize", syncSize);
    return () => {
      alive = false;
      window.cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", syncSize);
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className={`tuning-interstitial${fading ? " is-fading" : ""} ${className}`.trim()}
      data-testid={testId}
      data-active={active ? "1" : "0"}
      aria-live="polite"
      aria-busy={active}
    >
      <canvas ref={canvasRef} className="tuning-interstitial-static" aria-hidden="true" />
      <p className="tuning-interstitial-copy" data-testid={`${testId}-copy`}>
        {phrase}
      </p>
    </div>
  );
}
