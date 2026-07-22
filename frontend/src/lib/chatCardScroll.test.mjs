import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CHAT_INLINE_CARDS_STREAMING_CLASS,
  INLINE_CARDS_STREAMING_MAX_HEIGHT_VH,
  REVIEW_BATCH_STREAMING_MAX_HEIGHT_VH,
  chatMediaStripClassName,
  chatMediaStripUsesNestedScroll,
} from "./chatCardScroll.js";
import { readAllStyles } from "./readStyles.mjs";

describe("chatMediaStripUsesNestedScroll", () => {
  it("is false for completed turns", () => {
    assert.equal(chatMediaStripUsesNestedScroll({}), false);
    assert.equal(chatMediaStripUsesNestedScroll({ streaming: false, loading: false }), false);
  });

  it("is true while streaming or loading", () => {
    assert.equal(chatMediaStripUsesNestedScroll({ streaming: true }), true);
    assert.equal(chatMediaStripUsesNestedScroll({ loading: true }), true);
    assert.equal(chatMediaStripUsesNestedScroll({ streaming: true, loading: true }), true);
  });
});

describe("chatMediaStripClassName", () => {
  it("returns only the base class when complete", () => {
    assert.equal(chatMediaStripClassName("inline-cards"), "inline-cards");
    assert.equal(
      chatMediaStripClassName("review-batch-strip", { streaming: false }),
      "review-batch-strip",
    );
  });

  it("appends the streaming class while streaming", () => {
    assert.equal(
      chatMediaStripClassName("inline-cards", { streaming: true }),
      `inline-cards ${CHAT_INLINE_CARDS_STREAMING_CLASS}`,
    );
    assert.equal(
      chatMediaStripClassName("review-batch-strip", { loading: true }),
      `review-batch-strip ${CHAT_INLINE_CARDS_STREAMING_CLASS}`,
    );
  });

  it("documents streaming max-height constants in a sensible range", () => {
    assert.ok(INLINE_CARDS_STREAMING_MAX_HEIGHT_VH >= 24);
    assert.ok(INLINE_CARDS_STREAMING_MAX_HEIGHT_VH <= 60);
    assert.ok(REVIEW_BATCH_STREAMING_MAX_HEIGHT_VH >= 20);
    assert.ok(REVIEW_BATCH_STREAMING_MAX_HEIGHT_VH <= INLINE_CARDS_STREAMING_MAX_HEIGHT_VH);
  });
});

describe("completed chat media strip CSS (no nested vertical scroll)", () => {
  const styles = readAllStyles();

  it("keeps completed inline-cards on overflow-y hidden (not visible)", () => {
    assert.match(
      styles,
      /\.chat-scroll-region\s+\.inline-cards\s*\{[^}]*overflow-y:\s*hidden/s,
    );
    assert.doesNotMatch(
      styles,
      /\.chat-scroll-region\s+\.inline-cards\s*\{[^}]*overflow-y:\s*visible/s,
    );
  });

  it("gates nested vertical scroll behind the streaming class", () => {
    assert.match(
      styles,
      /\.chat-scroll-region\s+\.inline-cards\.chat-inline-cards--streaming\s*\{[^}]*overflow-y:\s*auto/s,
    );
    assert.match(
      styles,
      /\.chat-scroll-region\s+\.review-batch-strip\.chat-inline-cards--streaming\s*\{[^}]*overflow-y:\s*auto/s,
    );
  });

  it("uses overflow:visible for completed review-batch strips", () => {
    assert.match(
      styles,
      /\.chat-scroll-region\s+\.review-batch-strip\s*\{[^}]*overflow:\s*visible/s,
    );
  });

  it("clips message-inner horizontally without creating vertical scroll via hidden", () => {
    assert.match(styles, /\.message-inner\s*\{[^}]*overflow-x:\s*clip/s);
  });
});
