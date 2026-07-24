/** Padding (px) between the pinned user message and the top of the viewport. */
export const CHAT_SCROLL_PADDING = 16;

/**
 * Distance from the bottom (px) below which we treat the user as "following"
 * the conversation (auto-scroll allowed).
 */
export const NEW_REPLY_THRESHOLD_PX = 120;

/**
 * Which message index to pin for a "latest turn" scroll.
 *
 * Normal chat turns pin the user question so the reply can grow beneath it.
 * Assistant-only entries (Surprise Me / mood chips) have no new user message —
 * pin the new assistant entry itself instead of an earlier question.
 *
 * @param {Array<string|null|undefined>} roles Message roles in transcript order
 * @returns {number} Index to pin, or -1 when empty
 */
export function resolveLatestTurnAnchorIndex(roles) {
  if (!Array.isArray(roles) || roles.length === 0) return -1;
  const last = roles.length - 1;
  const lastRole = roles[last];
  if (lastRole === "user") return last;
  if (
    (lastRole === "assistant" || lastRole === "error" || lastRole === "system") &&
    last > 0 &&
    roles[last - 1] === "user"
  ) {
    return last - 1;
  }
  return last;
}

/**
 * Compute scrollTop so the latest user turn stays near the top of the viewport
 * while as much of the reply below it as practical remains visible.
 *
 * Priority when the reply is long:
 * 1. Keep the user message visible (pinned near top)
 * 2. Show the start of the assistant reply beneath it
 * 3. Do not yank so hard that the question scrolls off
 *
 * @param {{ viewportHeight: number, scrollHeight: number, userTop: number, padding?: number }} opts
 * @returns {number}
 */
export function computeFollowScrollTop({
  viewportHeight,
  scrollHeight,
  userTop,
  padding = CHAT_SCROLL_PADDING,
}) {
  const maxScroll = Math.max(0, scrollHeight - viewportHeight);
  // Pin the user message near the top so the reply can grow below it.
  const pinUserNearTop = Math.max(0, userTop - padding);
  // Never scroll past the end of the thread.
  return Math.min(pinUserNearTop, maxScroll);
}

/**
 * True when the user has scrolled up far enough that we should not force-scroll.
 * @param {{ scrollHeight: number, scrollTop: number, clientHeight: number, threshold?: number }} opts
 */
export function isScrolledAwayFromBottom({
  scrollHeight,
  scrollTop,
  clientHeight,
  threshold = NEW_REPLY_THRESHOLD_PX,
}) {
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
  return distanceFromBottom > threshold;
}

/**
 * Decide how a messages/loading update should move the scroll position.
 *
 * Rules:
 * - A brand-new turn scrolls the latest turn into view once ("pin-latest"),
 *   but only if the user was already following or is currently near the bottom.
 *   If they had scrolled away, we don't move them.
 * - While a reply is streaming (not a new turn), we only "stick-bottom" when the
 *   user is genuinely near the bottom right now. We NEVER re-pin to the top of
 *   the response on each streamed chunk, and we never yank a user who has
 *   scrolled away.
 *
 * @param {{ isNewTurn: boolean, streaming: boolean, nearBottom: boolean, wasFollowing: boolean }} opts
 * @returns {"pin-latest" | "stick-bottom" | "none"}
 */
export function resolveAutoScroll({ isNewTurn, streaming, nearBottom, wasFollowing }) {
  if (isNewTurn) {
    return wasFollowing || nearBottom ? "pin-latest" : "none";
  }
  if (streaming && nearBottom) {
    return "stick-bottom";
  }
  return "none";
}
