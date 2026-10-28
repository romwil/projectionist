import type {JsonObject, JsParam} from "../api/types";
/**
 * Place a Live guide / Up-next programme card inside the visible guide.
 *
 * A cell near the bottom used to open the card downward, so the synopsis and
 * the Open title details link fell outside the guide and were clipped.
 */

export const PROGRAM_HOVER_GAP = 6;
export const PROGRAM_HOVER_MARGIN = 8;

/**
 * @param {object} options
 * @param {{ top: number, bottom: number, left: number }} options.anchor
 * @param {number} options.cardWidth
 * @param {number} options.cardHeight
 * @param {{ top: number, right: number, bottom: number, left: number }} options.bounds
 * @param {number} [options.gap]
 * @param {number} [options.margin]
 * @param {number} [options.linkHeight] Height of the view link pinned to the card bottom.
 */
export function placeProgramHoverCard(
  {
  anchor,
  cardWidth,
  cardHeight,
  bounds,
  gap = PROGRAM_HOVER_GAP,
  margin = PROGRAM_HOVER_MARGIN,
  linkHeight = 0,
}: JsParam,
) {
  const width = Math.max(0, Number(cardWidth) || 0);
  const height = Math.max(0, Number(cardHeight) || 0);
  const link = Math.max(0, Math.min(Number(linkHeight) || 0, height));
  const maxHeight = Math.max(0, bounds.bottom - bounds.top - margin * 2);
  const visibleHeight = Math.min(height, maxHeight);
  const roomBelow = bounds.bottom - margin - (anchor.bottom + gap);
  const roomAbove = anchor.top - gap - (bounds.top + margin);
  const openUp = roomBelow < visibleHeight && roomAbove >= roomBelow;

  let top = openUp ? anchor.top - gap - visibleHeight : anchor.bottom + gap;
  const minTop = bounds.top + margin;
  const maxTop = bounds.bottom - margin - visibleHeight;
  if (maxTop >= minTop) {
    top = Math.min(Math.max(top, minTop), maxTop);
  } else {
    top = minTop;
  }

  const minLeft = bounds.left + margin;
  const maxLeft = bounds.right - margin - width;
  let left = anchor.left;
  if (maxLeft >= minLeft) {
    left = Math.min(Math.max(left, minLeft), maxLeft);
  } else {
    left = minLeft;
  }

  const viewLinkBottom = top + visibleHeight;
  const viewLinkTop = viewLinkBottom - (visibleHeight > 0 ? Math.min(link, visibleHeight) : 0);

  return {
    top,
    left,
    maxHeight,
    visibleHeight,
    openUp,
    viewLinkTop,
    viewLinkBottom,
  };
}
