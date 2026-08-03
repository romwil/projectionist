/** Pure helpers for Year in Review cinema reel. */

export const YIR_DEFAULT_DURATION_MS = 5500;

/**
 * @param {Array<{ duration_ms?: number }>} chapters
 * @param {number} index
 */
export function chapterDurationMs(chapters, index) {
  const chapter = Array.isArray(chapters) ? chapters[index] : null;
  const raw = Number(chapter?.duration_ms);
  if (Number.isFinite(raw) && raw >= 2000) return raw;
  return YIR_DEFAULT_DURATION_MS;
}

/**
 * @param {number} index
 * @param {number} total
 */
export function nextChapterIndex(index, total) {
  if (!total || total < 1) return 0;
  return Math.min(Math.max(0, index) + 1, total - 1);
}

/**
 * @param {number} index
 * @param {number} total
 */
export function prevChapterIndex(index, total) {
  if (!total || total < 1) return 0;
  return Math.max(0, Math.min(total - 1, index) - 1);
}

/**
 * Share-card text for a chapter (clipboard fallback when image copy unsupported).
 * @param {{ title?: string, body?: string }} chapter
 * @param {number} year
 */
export function shareCardText(chapter, year) {
  const title = String(chapter?.title || "Year in Review").trim();
  const body = String(chapter?.body || "").trim();
  return [`Projectionist · ${year}`, title, body].filter(Boolean).join("\n\n");
}

/**
 * Whether auto-advance should run given pause + reduced-motion prefs.
 */
export function shouldAutoAdvance({ paused, prefersReducedMotion }) {
  if (paused) return false;
  if (prefersReducedMotion) return false;
  return true;
}

export function yirPath(year) {
  return `/year-in-review/${Number(year) || ""}`;
}
