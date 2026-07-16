import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CHAT_SCROLL_REGION_CLASS,
  MESSAGE_CONTAINMENT_CLASSES,
  isHorizontallyContained,
  messageTextContainmentStyle,
} from "./chatLayout.js";

describe("chatLayout containment", () => {
  it("exposes stable class names for the transcript shell", () => {
    assert.equal(CHAT_SCROLL_REGION_CLASS, "chat-scroll-region");
    assert.ok(MESSAGE_CONTAINMENT_CLASSES.includes("message-contained"));
  });

  it("treats overflow clipping as horizontally contained", () => {
    assert.equal(isHorizontallyContained({ overflowX: "hidden" }), true);
    assert.equal(isHorizontallyContained({ overflowX: "clip" }), true);
    assert.equal(isHorizontallyContained({ overflow: "auto" }), true);
  });

  it("treats wrap + width bounds as contained", () => {
    assert.equal(
      isHorizontallyContained({
        overflowWrap: "anywhere",
        minWidth: "0",
        maxWidth: "100%",
      }),
      true,
    );
    assert.equal(isHorizontallyContained({ overflowWrap: "normal" }), false);
  });

  it("messageTextContainmentStyle returns viewport-safe defaults", () => {
    const style = messageTextContainmentStyle();
    assert.equal(isHorizontallyContained(style), true);
    assert.equal(style.overflowX, "hidden");
    assert.equal(style.minWidth, "0");
  });
});
