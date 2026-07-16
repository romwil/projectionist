/**
 * Chat transcript layout containment helpers.
 * Keeps long markdown / media strips from expanding the workspace viewport.
 */

/** CSS class applied to the scrollable transcript host. */
export const CHAT_SCROLL_REGION_CLASS = "chat-scroll-region";

/** CSS containment classes for assistant/user message shells. */
export const MESSAGE_CONTAINMENT_CLASSES = ["message", "message-contained"];

/**
 * True when a style object (or CSS declaration map) keeps content inside
 * a bounded horizontal box instead of growing the page width.
 */
export function isHorizontallyContained(style = {}) {
  const overflowX = String(style.overflowX || style.overflow || "").toLowerCase();
  const wrap = String(style.overflowWrap || style.wordBreak || "").toLowerCase();
  const minWidth = String(style.minWidth || "");
  const maxWidth = String(style.maxWidth || "");

  const clipsOverflow = ["hidden", "clip", "auto", "scroll"].includes(overflowX);
  const wrapsText = wrap.includes("break") || wrap === "anywhere" || wrap === "break-word";
  const widthBounded = minWidth === "0" || minWidth === "0px" || maxWidth === "100%";

  return clipsOverflow || (wrapsText && widthBounded);
}

/**
 * Recommended inline containment for markdown / message text hosts.
 */
export function messageTextContainmentStyle() {
  return {
    minWidth: "0",
    maxWidth: "100%",
    overflowWrap: "anywhere",
    wordBreak: "break-word",
    overflowX: "hidden",
  };
}
