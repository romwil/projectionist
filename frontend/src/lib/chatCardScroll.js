/**
 * CSS class helpers for chat media-card scroll containment.
 *
 * Nested vertical scroll is allowed only while an assistant turn is still
 * streaming. Once the turn completes, strips size to their natural height
 * (one poster row for inline cards) and only `.chat-scroll-region` scrolls.
 *
 * CSS note: do not pair `overflow-x: auto|hidden` with `overflow-y: visible`
 * on completed strips — the cascade computes visible → auto and recreates a
 * nested vertical scrollport (classic horizontal-scrollbar height bleed).
 */

/** Class toggled on chat media strips / activity panels while streaming. */
export const CHAT_INLINE_CARDS_STREAMING_CLASS = "chat-inline-cards--streaming";

/** Temporary max-height (vh) used by CSS while streaming — documented for tests. */
export const INLINE_CARDS_STREAMING_MAX_HEIGHT_VH = 42;

/** Temporary max-height (vh) for review-batch strips while streaming. */
export const REVIEW_BATCH_STREAMING_MAX_HEIGHT_VH = 36;

/**
 * Whether a chat media strip should use temporary nested vertical scroll.
 * @param {{ streaming?: boolean, loading?: boolean }} [flags]
 * @returns {boolean}
 */
export function chatMediaStripUsesNestedScroll({ streaming = false, loading = false } = {}) {
  return Boolean(streaming || loading);
}

/**
 * Class list for chat media strips under `.chat-scroll-region`.
 * Adds {@link CHAT_INLINE_CARDS_STREAMING_CLASS} only while streaming/loading.
 *
 * @param {string} baseClass e.g. `"inline-cards"` or `"review-batch-strip"`
 * @param {{ streaming?: boolean, loading?: boolean }} [flags]
 * @returns {string}
 */
export function chatMediaStripClassName(baseClass, { streaming = false, loading = false } = {}) {
  const base = String(baseClass || "").trim();
  if (!chatMediaStripUsesNestedScroll({ streaming, loading })) return base;
  return `${base} ${CHAT_INLINE_CARDS_STREAMING_CLASS}`.trim();
}
