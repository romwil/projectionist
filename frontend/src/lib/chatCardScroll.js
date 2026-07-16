/**
 * CSS class helpers / constants for chat media-card scroll containment.
 * Kept extractable so layout rules can be unit-tested without the full stylesheet.
 */

/** Max height for inline title-card strips inside the chat transcript. */
export const INLINE_CARDS_MAX_HEIGHT_VH = 42;

/** Max height for compact review-batch strips inside chat. */
export const REVIEW_BATCH_MAX_HEIGHT_VH = 36;

/**
 * Build inline style object for a scrollable card strip.
 * @param {number} maxVh
 * @returns {{ maxHeight: string, overflowY: string, overflowX: string }}
 */
export function scrollableCardStripStyle(maxVh = INLINE_CARDS_MAX_HEIGHT_VH) {
  const vh = Math.max(12, Math.min(80, Number(maxVh) || INLINE_CARDS_MAX_HEIGHT_VH));
  return {
    maxHeight: `${vh}vh`,
    overflowY: "auto",
    overflowX: "auto",
  };
}
