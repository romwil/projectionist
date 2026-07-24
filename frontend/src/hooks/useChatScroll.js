import { useCallback, useEffect, useRef, useState } from "react";
import {
  CHAT_SCROLL_PADDING,
  computeFollowScrollTop,
  isScrolledAwayFromBottom,
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

  const scrollToBottom = useCallback((behavior = "auto") => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
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

    const messageNodes = el.querySelectorAll("[data-message-role]");
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
    el.scrollTo({ top, behavior });
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

  useEffect(() => {
    if (prevSessionRef.current !== sessionId) {
      prevSessionRef.current = sessionId;
      prevCountRef.current = messages.length;
      followingRef.current = true;
      setShowNewReplyChip(false);
      requestAnimationFrame(() => scrollToBottom("auto"));
    }
  }, [sessionId, messages.length, scrollToBottom]);

  useEffect(() => {
    const count = messages.length;
    if (count === 0) {
      prevCountRef.current = 0;
      setShowNewReplyChip(false);
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
        // A brand-new turn: bring the latest user turn near the top once so the
        // question stays visible while the reply grows below it.
        scrollToLatestTurn("smooth");
        return;
      }

      if (action === "stick-bottom") {
        // User is reading at the bottom while the reply streams — keep them
        // pinned to the bottom. Never re-pin to the top of the response.
        scrollToBottom("auto");
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
