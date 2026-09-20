import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  CHAT_SCROLL_REGION_CLASS,
  MESSAGE_CONTAINMENT_CLASSES,
  NEW_REPLY_CHIP_CLASS,
  isHorizontallyContained,
  messageTextContainmentStyle,
} from "./chatLayout.js";
import { readAllStyles } from "./readStyles.mjs";

describe("chatLayout containment", () => {
  it("exposes stable class names for the transcript shell", () => {
    assert.equal(CHAT_SCROLL_REGION_CLASS, "chat-scroll-region");
    assert.equal(NEW_REPLY_CHIP_CLASS, "new-reply-chip");
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
    assert.equal(style.overflowX, "clip");
    assert.equal(style.minWidth, "0");
  });
});

describe("new reply chip placement", () => {
  const styles = readAllStyles();

  it("does not use sticky positioning that would overlay transcript bubbles", () => {
    const chipBlock = styles.match(/\.new-reply-chip\s*\{[^}]*\}/s)?.[0] || "";
    assert.match(chipBlock, /flex-shrink:\s*0/);
    assert.match(chipBlock, /align-self:\s*center/);
    assert.doesNotMatch(chipBlock, /position:\s*sticky/);
    assert.doesNotMatch(styles, /\.chat-scroll-region[^{]*\{[^}]*\.new-reply-chip/s);
  });

  it("workspace-main is the flex column that owns transcript, chip, and composer", () => {
    const block = styles.match(/\.workspace-main\s*\{[^}]*\}/s)?.[0] || "";
    assert.match(block, /display:\s*flex/);
    assert.match(block, /flex-direction:\s*column/);
  });

  it("renders as a sibling between the scroll region and the composer", () => {
    const appJsx = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
    const workspace = appJsx.match(/<main className="workspace-main"[^>]*>[\s\S]*?<\/main>/)?.[0] || "";
    assert.match(workspace, /<NewReplyChip\b/);

    const scrollOpenAt = workspace.indexOf(`<div className="${CHAT_SCROLL_REGION_CLASS}"`);
    const chipAt = workspace.indexOf("<NewReplyChip");
    const composerAt = workspace.search(/className="composer[\s"]/);
    assert.ok(scrollOpenAt >= 0, "chat-scroll-region opens in workspace-main");
    assert.ok(chipAt > scrollOpenAt, "chip follows the transcript");
    assert.ok(composerAt > chipAt, "chip precedes the composer");

    const betweenScrollAndChip = workspace.slice(scrollOpenAt, chipAt);
    const opens = (betweenScrollAndChip.match(/<div\b/g) || []).length;
    const closes = (betweenScrollAndChip.match(/<\/div>/g) || []).length;
    assert.equal(opens, closes, "chat-scroll-region is closed before NewReplyChip");
  });
});
