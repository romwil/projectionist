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

/**
 * Recap share text — the screenshot-in-words beat.
 * @param {object|null|undefined} recap
 * @param {number} year
 */
export function recapShareText(recap, year) {
  if (!recap || typeof recap !== "object") return `Projectionist · ${year}`;
  const lines = [`Projectionist · ${year}`];
  if (recap.headline) lines.push(String(recap.headline));
  const hero = Array.isArray(recap.hero) ? recap.hero : [];
  for (const item of hero) {
    const value = String(item?.value || "").trim();
    const label = String(item?.label || "").trim();
    if (value && label) lines.push(`${value} ${label}`);
  }
  if (recap.movie_genre?.name) {
    lines.push(`Movies: ${recap.movie_genre.name}`);
  }
  if (recap.tv_genre?.name) {
    lines.push(`TV: ${recap.tv_genre.name}`);
  }
  return lines.filter(Boolean).join("\n");
}

/**
 * Whether the linger recap sheet should render (ready reels only).
 */
export function recapIsReady(reel) {
  return Boolean(reel?.recap) && String(reel?.status || "") === "ready";
}

/**
 * Month bars for the recap chart. Values 0–1 relative to the peak month.
 * @param {Record<string, number>|null|undefined} monthlyCounts
 */
export function monthBarPercents(monthlyCounts) {
  const counts = monthlyCounts && typeof monthlyCounts === "object" ? monthlyCounts : {};
  const values = Array.from({ length: 12 }, (_, i) => Number(counts[String(i + 1)] || counts[i + 1] || 0));
  const peak = Math.max(0, ...values);
  return values.map((n) => (peak > 0 ? n / peak : 0));
}

/**
 * Durable reel path from an admin generate response — only when the snapshot is viewable.
 * Prefer API `path`; never invent a link for empty / not-ready status.
 * @param {{ path?: string|null, year?: number, status?: string, delivered?: number }|null|undefined} result
 */
export function yirPathFromGenerateResult(result) {
  if (!result || typeof result !== "object") return null;
  const status = result.status != null ? String(result.status) : "";
  if (status === "empty") return null;
  const explicit = result.path != null ? String(result.path).trim() : "";
  if (explicit.startsWith("/year-in-review/")) return explicit;
  if (status && status !== "ready" && status !== "tease") return null;
  const year = Number(result.year);
  if (!Number.isFinite(year) || year < 2000) return null;
  // Without a status, only trust a successful inbox delivery.
  if (!status && !(Number(result.delivered) > 0)) return null;
  return yirPath(year);
}
