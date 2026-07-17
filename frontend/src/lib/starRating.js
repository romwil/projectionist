/** Half-star rating helpers (0.5–5.0 in 0.5 steps). */

export const STAR_STEPS = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];
export const STAR_MIN = 0.5;
export const STAR_MAX = 5;
export const STAR_STEP = 0.5;

export function clampStars(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return 0;
  const half = Math.round(num * 2) / 2;
  if (half < STAR_MIN) return STAR_MIN;
  if (half > STAR_MAX) return STAR_MAX;
  return half;
}

export function formatStarsLabel(stars) {
  const value = Number(stars);
  if (!Number.isFinite(value) || value <= 0) return "";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** Visual fill for star index `full` (1–5) given a display rating. */
export function starFillForValue(display, full) {
  const value = Number(display) || 0;
  const whole = Number(full);
  if (value >= whole) return "full";
  if (value >= whole - 0.5) return "half";
  return "empty";
}

/**
 * Keyboard step for a slider-style star picker.
 * Returns next value, or null when the key is not handled.
 */
export function starValueFromKey(key, current) {
  const now = clampStars(current);
  const baseline = now > 0 ? now : 0;
  switch (key) {
    case "ArrowRight":
    case "ArrowUp":
      return clampStars(Math.max(STAR_MIN, baseline + STAR_STEP));
    case "ArrowLeft":
    case "ArrowDown":
      if (baseline <= STAR_MIN) return 0;
      return clampStars(baseline - STAR_STEP);
    case "Home":
      return STAR_MIN;
    case "End":
      return STAR_MAX;
    default:
      return null;
  }
}

/** Map pointer X within a star unit to half or full step for that star. */
export function starValueFromPointerX(clientX, element, fullStar) {
  if (!element || !Number.isFinite(fullStar)) return null;
  const rect = element.getBoundingClientRect();
  if (!rect.width) return fullStar;
  const ratio = (clientX - rect.left) / rect.width;
  return ratio < 0.5 ? fullStar - 0.5 : fullStar;
}
