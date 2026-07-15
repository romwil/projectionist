import { useCallback, useEffect, useRef, useState } from "react";
import {
  CHAT_SCROLL_PADDING,
  computeFollowScrollTop,
  isScrolledAwayFromBottom,
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
   * Keep the latest user question near the top of the viewport so the
   * assistant reply (or typing indicator) can grow beneath it without
   * yanking the question off-screen.
   */
  const scrollToLatestTurn = useCallback((behavior = "smooth") => {
    const el = scrollRef.current;
    if (!el) return;

    const userNodes = el.querySelectorAll('[data-message-role="user"]');
    const userNode = userNodes.length ? userNodes[userNodes.length - 1] : null;
    if (!userNode) {
      scrollToBottom(behavior);
      return;
    }

    const top = computeFollowScrollTop({
      viewportHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      userTop: userNode.offsetTop,
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

    requestAnimationFrame(() => {
      if (!wasFollowing) {
        // Re-check actual scroll position — content growth during streaming
        // can change scrollHeight without user interaction, so verify we're
        // genuinely scrolled away before showing the chip.
        if (!isScrolledUp()) {
          followingRef.current = true;
          return;
        }
        if (isNewMessage || loading) {
          setShowNewReplyChip(true);
        }
        return;
      }

      // Following: pin the latest user turn near the top so the question
      // stays visible while the reply / typing indicator grows below.
      if (isNewMessage && (last.role === "user" || last.role === "assistant" || last.role === "error")) {
        scrollToLatestTurn("smooth");
        return;
      }

      if (loading) {
        scrollToLatestTurn("smooth");
      }
    });
  }, [messages, loading, scrollToLatestTurn, isScrolledUp]);

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
