/**
 * Chat transcript layout containment helpers.
 * Keeps long markdown / media strips from expanding the workspace viewport.
 */

/** CSS class applied to the scrollable transcript host. */
export const CHAT_SCROLL_REGION_CLASS = "chat-scroll-region";

/** Phone Play (390×844) opens the Plex client; composer stays pinned. */
export const PHONE_PLAY_MAX_WIDTH = 390;

/** CSS class for the New reply chip — lives above the composer, not in the transcript. */
export const NEW_REPLY_CHIP_CLASS = "new-reply-chip";

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
 * Prefer overflow-x: clip so overflow-y stays non-scrolling (hidden/auto on X
 * forces visible Y to compute to auto per CSS Overflow).
 */
export function messageTextContainmentStyle() {
  return {
    minWidth: "0",
    maxWidth: "100%",
    overflowWrap: "anywhere",
    wordBreak: "break-word",
    overflowX: "clip",
  };
}

export function isPhonePlayViewport(width) {
  const value = Number(width);
  if (Number.isFinite(value) && value > 0) return value <= PHONE_PLAY_MAX_WIDTH;
  if (typeof window !== "undefined" && Number.isFinite(window.innerWidth)) {
    return window.innerWidth <= PHONE_PLAY_MAX_WIDTH;
  }
  return false;
}

/** Most recently updated thread that is not the empty chat-home session. */
export function pickResumeThread(threads, activeSessionId) {
  const active = String(activeSessionId || "").trim();
  const list = Array.isArray(threads) ? threads : [];
  return (
    list.find((thread) => {
      const id = String(thread?.id || "").trim();
      if (!id || id === active) return false;
      return Boolean(String(thread?.thread_title || "").trim());
    }) || null
  );
}

export function resumeChipFromThread(thread) {
  if (!thread?.id) return null;
  const title = String(thread.thread_title || "").trim() || "last chat";
  return {
    id: "resume",
    label: `Resume ${title}`,
    testId: "chat-resume-chip",
    action: { type: "resume", threadId: String(thread.id) },
  };
}

/** Saved-library shelf on chat home — no extra H1; existing Save to library. */
export function holdableShelfPages(pages, { limit = 6 } = {}) {
  const list = Array.isArray(pages) ? pages : [];
  return list
    .filter((page) => page?.id && String(page.name || "").trim())
    .slice(0, Math.max(0, Number(limit) || 0));
}
