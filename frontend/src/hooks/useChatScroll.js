import { useCallback, useEffect, useRef, useState } from "react";
import {
  CHAT_SCROLL_PADDING,
  applyChatScroll,
  computeFollowScrollTop,
  isScrolledAwayFromBottom,
  isTranscriptRestore,
  resolveAutoScroll,
  resolveLatestTurnAnchorIndex,
} from "../lib/chatScroll.js";

export default function useChatScroll({ messages, loading, sessionId }) {
  const scrollRef = useRef(null);
  const prevSessionRef = useRef(sessionId);
  const prevCountRef = useRef(0);
  const followingRef = useRef(true);
  const [showNewReplyChip, setShowNewReplyChip] = useState(false);

  const isScrolledUp = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return false;
    return isScrolledAwayFromBottom({
      scrollHeight: el.scrollHeight,
      scrollTop: el.scrollTop,
      clientHeight: el.clientHeight,
    });
  }, []);

  const scrollToBottom = useCallback((behavior = "instant") => {
    const el = scrollRef.current;
    if (!el) return;
    applyChatScroll(el, el.scrollHeight, behavior);
    followingRef.current = true;
    setShowNewReplyChip(false);
  }, []);

  /**
   * Bring the latest turn into view. For a normal Q&A turn, pin the user
   * question near the top so the reply can grow beneath it. For assistant-only
   * entries (Surprise Me / mood chips), pin the new assistant message itself —
   * never an earlier user turn from the same thread.
   */
  const scrollToLatestTurn = useCallback((behavior = "smooth") => {
    const el = scrollRef.current;
    if (!el) return;

    const messageNodes = el.querySelectorAll(
      "[data-message-role]:not([data-message-kind='review-prompt'])",
    );
    const roles = Array.from(messageNodes, (node) => node.getAttribute("data-message-role"));
    const anchorIndex = resolveLatestTurnAnchorIndex(roles);
    const targetNode = anchorIndex >= 0 ? messageNodes[anchorIndex] : null;
    if (!targetNode) {
      scrollToBottom(behavior);
      return;
    }

    const top = computeFollowScrollTop({
      viewportHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      userTop: targetNode.offsetTop,
      padding: CHAT_SCROLL_PADDING,
    });
    applyChatScroll(el, top, behavior);
    followingRef.current = true;
    setShowNewReplyChip(false);
  }, [scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;

    function handleScroll() {
      const away = isScrolledAwayFromBottom({
        scrollHeight: el.scrollHeight,
        scrollTop: el.scrollTop,
        clientHeight: el.clientHeight,
      });
      followingRef.current = !away;
      if (!away) {
        setShowNewReplyChip(false);
      }
    }

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  // Session switch: reset counters so the next transcript paint restores instantly.
  useEffect(() => {
    if (prevSessionRef.current === sessionId) return;
    prevSessionRef.current = sessionId;
    prevCountRef.current = 0;
    followingRef.current = true;
    setShowNewReplyChip(false);
    if (messages.length > 0) {
      prevCountRef.current = messages.length;
      requestAnimationFrame(() => scrollToBottom("instant"));
    }
  }, [sessionId, messages.length, scrollToBottom]);

  useEffect(() => {
    const count = messages.length;
    if (count === 0) {
      prevCountRef.current = 0;
      setShowNewReplyChip(false);
      return;
    }

    // Remount / navigate back / async thread load: land at the bottom with no
    // smooth scroll-through of the whole history.
    if (isTranscriptRestore({ prevCount: prevCountRef.current, nextCount: count })) {
      prevCountRef.current = count;
      followingRef.current = true;
      setShowNewReplyChip(false);
      requestAnimationFrame(() => scrollToBottom("instant"));
      return;
    }

    const isNewMessage = count > prevCountRef.current;
    if (!isNewMessage && !loading) return;

    const last = messages[count - 1];
    const wasFollowing = followingRef.current;
    if (isNewMessage) {
      prevCountRef.current = count;
    }

    const isNewTurn =
      isNewMessage &&
      (last.role === "user" || last.role === "assistant" || last.role === "error");

    requestAnimationFrame(() => {
      // Use the *actual* scroll position, not a stale following flag: content
      // growth during streaming changes scrollHeight without user interaction.
      const nearBottom = !isScrolledUp();
      const action = resolveAutoScroll({
        isNewTurn,
        streaming: loading,
        nearBottom,
        wasFollowing,
      });

      if (action === "pin-latest") {
        // Live new turn only — smooth is OK here. Restore path never reaches this.
        scrollToLatestTurn("smooth");
        return;
      }

      if (action === "stick-bottom") {
        // User is reading at the bottom while the reply streams — keep them
        // pinned to the bottom. Never re-pin to the top of the response.
        scrollToBottom("instant");
        return;
      }

      // Otherwise leave the scroll position untouched. Surface the "new reply"
      // chip when there is fresh content below and the user is scrolled away.
      if (nearBottom) {
        followingRef.current = true;
        return;
      }
      followingRef.current = false;
      if (isNewMessage || loading) {
        setShowNewReplyChip(true);
      }
    });
  }, [messages, loading, scrollToLatestTurn, scrollToBottom, isScrolledUp]);

  // When loading ends (streaming finishes) and user is at/near bottom, dismiss
  // the chip — the scroll handler won't fire if no scroll actually happens.
  useEffect(() => {
    if (loading || !showNewReplyChip) return;
    if (!isScrolledUp()) {
      followingRef.current = true;
      setShowNewReplyChip(false);
    }
  }, [loading, showNewReplyChip, isScrolledUp]);

  return { scrollRef, showNewReplyChip, scrollToBottom, scrollToLatestTurn };
}
