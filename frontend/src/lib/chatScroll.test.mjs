import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CHAT_SCROLL_PADDING,
  computeFollowScrollTop,
  isScrolledAwayFromBottom,
  resolveAutoScroll,
  resolveLatestTurnAnchorIndex,
} from "./chatScroll.js";

describe("computeFollowScrollTop", () => {
  it("pins the latest user message near the top of the viewport", () => {
    const scrollTop = computeFollowScrollTop({
      viewportHeight: 800,
      scrollHeight: 2400,
      userTop: 1200,
      padding: 16,
    });
    assert.equal(scrollTop, 1200 - 16);
  });

  it("does not scroll past the bottom of the thread", () => {
    const scrollTop = computeFollowScrollTop({
      viewportHeight: 800,
      scrollHeight: 900,
      userTop: 500,
      padding: 16,
    });
    // maxScroll = 100; pin would be 484 → clamp to 100
    assert.equal(scrollTop, 100);
  });

  it("keeps scroll at 0 when the turn already fits at the top", () => {
    const scrollTop = computeFollowScrollTop({
      viewportHeight: 800,
      scrollHeight: 600,
      userTop: 40,
      padding: 16,
    });
    assert.equal(scrollTop, 0);
  });

  it("uses CHAT_SCROLL_PADDING by default", () => {
    const scrollTop = computeFollowScrollTop({
      viewportHeight: 800,
      scrollHeight: 2000,
      userTop: 400,
    });
    assert.equal(scrollTop, 400 - CHAT_SCROLL_PADDING);
  });

  it("for a tall reply, keeps the question in view instead of jumping to the bottom", () => {
    const viewportHeight = 700;
    const userTop = 1000;
    const replyHeight = 3000;
    const scrollHeight = userTop + 80 + replyHeight;
    const followTop = computeFollowScrollTop({
      viewportHeight,
      scrollHeight,
      userTop,
      padding: 16,
    });
    const jumpToBottom = scrollHeight - viewportHeight;

    // Following scroll keeps user near top…
    assert.equal(followTop, userTop - 16);
    // …while a naive jump-to-bottom would push the question off-screen.
    assert.ok(jumpToBottom > userTop + 80);
    assert.ok(followTop < userTop);
    // User message top remains in the viewport after follow scroll.
    assert.ok(userTop >= followTop);
    assert.ok(userTop < followTop + viewportHeight);
  });
});

describe("isScrolledAwayFromBottom", () => {
  it("is false when near the bottom", () => {
    assert.equal(
      isScrolledAwayFromBottom({
        scrollHeight: 2000,
        scrollTop: 1250,
        clientHeight: 700,
        threshold: 120,
      }),
      false
    );
  });

  it("is true when intentionally scrolled up", () => {
    assert.equal(
      isScrolledAwayFromBottom({
        scrollHeight: 2000,
        scrollTop: 200,
        clientHeight: 700,
        threshold: 120,
      }),
      true
    );
  });
});

describe("resolveAutoScroll", () => {
  it("pins the latest turn into view when a new turn starts and the user was following", () => {
    assert.equal(
      resolveAutoScroll({ isNewTurn: true, streaming: false, nearBottom: false, wasFollowing: true }),
      "pin-latest"
    );
  });

  it("pins the latest turn when a new turn starts and the user is near the bottom", () => {
    assert.equal(
      resolveAutoScroll({ isNewTurn: true, streaming: true, nearBottom: true, wasFollowing: false }),
      "pin-latest"
    );
  });

  it("does not move for a new turn if the user had scrolled away", () => {
    assert.equal(
      resolveAutoScroll({ isNewTurn: true, streaming: false, nearBottom: false, wasFollowing: false }),
      "none"
    );
  });

  it("sticks to the bottom while streaming only when the user is near the bottom", () => {
    assert.equal(
      resolveAutoScroll({ isNewTurn: false, streaming: true, nearBottom: true, wasFollowing: true }),
      "stick-bottom"
    );
  });

  it("never yanks the user back while streaming after they scroll away (no top pin per chunk)", () => {
    // The core regression: a streamed chunk must not force the view anywhere
    // once the user has scrolled up.
    assert.equal(
      resolveAutoScroll({ isNewTurn: false, streaming: true, nearBottom: false, wasFollowing: true }),
      "none"
    );
    assert.equal(
      resolveAutoScroll({ isNewTurn: false, streaming: true, nearBottom: false, wasFollowing: false }),
      "none"
    );
  });

  it("does nothing for non-streaming updates that are not new turns", () => {
    assert.equal(
      resolveAutoScroll({ isNewTurn: false, streaming: false, nearBottom: true, wasFollowing: true }),
      "none"
    );
  });
});

describe("resolveLatestTurnAnchorIndex", () => {
  it("pins the user message for a normal Q&A turn", () => {
    assert.equal(resolveLatestTurnAnchorIndex(["user", "assistant", "user", "assistant"]), 2);
    assert.equal(resolveLatestTurnAnchorIndex(["user"]), 0);
  });

  it("pins the new assistant entry for Surprise Me (no new user message)", () => {
    assert.equal(resolveLatestTurnAnchorIndex(["user", "assistant", "assistant"]), 2);
    assert.equal(resolveLatestTurnAnchorIndex(["assistant"]), 0);
  });

  it("returns -1 for an empty transcript", () => {
    assert.equal(resolveLatestTurnAnchorIndex([]), -1);
    assert.equal(resolveLatestTurnAnchorIndex(null), -1);
  });
});
