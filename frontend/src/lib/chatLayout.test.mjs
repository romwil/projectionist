import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { savedLibraryChatHref } from "./backNav.js";
import {
  CHAT_SCROLL_REGION_CLASS,
  MESSAGE_CONTAINMENT_CLASSES,
  NEW_REPLY_CHIP_CLASS,
  PHONE_PLAY_MAX_LONG_EDGE,
  PHONE_PLAY_MAX_SHORT_EDGE,
  PHONE_PLAY_MAX_WIDTH,
  holdableShelfPages,
  isCompactPlayViewport,
  isHorizontallyContained,
  isPhonePlayViewport,
  messageTextContainmentStyle,
  pickResumeThread,
  resumeChipFromThread,
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
    const appJsx = readFileSync(new URL("../components/ChatWorkspace.jsx", import.meta.url), "utf8");
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

describe("1.36.5 whisper/tonight chat home", () => {
  it("treats phone portrait and landscape as phone Play viewports", () => {
    assert.equal(PHONE_PLAY_MAX_WIDTH, 390);
    assert.equal(PHONE_PLAY_MAX_SHORT_EDGE, 500);
    assert.equal(PHONE_PLAY_MAX_LONG_EDGE, 932);
    // Legacy one-arg width-only (portrait reference / unknown height).
    assert.equal(isPhonePlayViewport(390), true);
    assert.equal(isPhonePlayViewport(844), false);
    assert.equal(isPhonePlayViewport(1024), false);
    // Explicit WxH: portrait and landscape iPhone-class stay phone.
    assert.equal(isPhonePlayViewport(390, 844), true);
    assert.equal(isPhonePlayViewport(844, 390), true);
    assert.equal(isPhonePlayViewport(932, 430), true);
    assert.equal(isPhonePlayViewport(1024, 768), false);
    assert.equal(isCompactPlayViewport(1024, 768), true);
    assert.equal(isCompactPlayViewport(1440, 900), false);
  });

  it("picks a resume chip for the latest other thread", () => {
    const resume = pickResumeThread(
      [
        { id: "empty-now", thread_title: "New chat" },
        { id: "last-night", thread_title: "Noir for Sunday" },
      ],
      "empty-now",
    );
    assert.equal(resume.id, "last-night");
    const chip = resumeChipFromThread(resume);
    assert.equal(chip.testId, "chat-resume-chip");
    assert.equal(chip.action.type, "resume");
    assert.equal(chip.action.threadId, "last-night");
    assert.match(chip.label, /Resume Noir for Sunday/);
  });

  it("builds a holdable shelf from saved library pages without inventing titles", () => {
    const shelf = holdableShelfPages(
      [
        { id: "p1", name: "Sunday stack" },
        { id: "", name: "skip" },
        { id: "p2", name: "  " },
        { id: "p3", name: "Keepers" },
      ],
      { limit: 2 },
    );
    assert.deepEqual(
      shelf.map((page) => page.id),
      ["p1", "p3"],
    );
  });

  it("saves to the holdable shelf without a prompt H1 and shows resume + shelf on chat home", () => {
    const appJsx = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
    const workspaceJsx = readFileSync(new URL("../components/ChatWorkspace.jsx", import.meta.url), "utf8");
    const libraryJsx = readFileSync(new URL("../pages/LibraryPage.jsx", import.meta.url), "utf8");
    assert.doesNotMatch(appJsx, /window\.prompt\(/);
    assert.doesNotMatch(workspaceJsx, /window\.prompt\(/);
    assert.match(workspaceJsx, /data-testid="holdable-shelf"/);
    assert.match(workspaceJsx, /savedLibraryChatHref\(page\.id\)/);
    assert.match(savedLibraryChatHref("sunday-stack"), /\/chat\?saved_library=/);
    assert.doesNotMatch(workspaceJsx, /\/\?saved_library=/);
    assert.doesNotMatch(libraryJsx, /\/\?saved_library=/);
    assert.match(libraryJsx, /savedLibraryChatHref\(/);
    assert.match(appJsx, /resumeChipFromThread/);
    assert.match(appJsx, /refreshSavedShelf/);
    assert.match(appJsx, /savedLibraryStartedRef\.current = false/);
    assert.match(appJsx, /arrServiceConnected/);
  });

  it("pins the composer at 390 so Play cannot push it off the phone fold", () => {
    const styles = readAllStyles();
    assert.match(
      styles,
      /@media \(max-width: 390px\)[\s\S]*?\.composer[\s\S]*?position:\s*sticky/s,
    );
    assert.match(
      styles,
      /@media \(max-width: 390px\)[\s\S]*?\.composer[\s\S]*?margin-top:\s*auto/s,
    );
  });
});
