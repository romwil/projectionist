import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  WHY_WORD_LIMIT,
  WHISPER_PATH,
  clipWhy,
  isForbiddenWhisperCopy,
  whisperHomeLabel,
  whisperInboxHeadline,
  whisperMemberName,
  whisperWhy,
  whyWordCount,
} from "./whisperInbox.js";

test("clipWhy hard-caps at twelve words", () => {
  const clipped = clipWhy("one two three four five six seven eight nine ten eleven twelve thirteen");
  assert.equal(whyWordCount(clipped), WHY_WORD_LIMIT);
  assert.equal(clipped.endsWith("twelve"), true);
});

test("whisper why never keeps download-complete copy", () => {
  assert.equal(isForbiddenWhisperCopy("Ada, download complete for Heat"), true);
  assert.equal(isForbiddenWhisperCopy("Ada, after Heat this one keeps that same mood."), false);
});

test("named member headline and home chip", () => {
  assert.equal(whisperInboxHeadline({ memberName: "Will", count: 1 }), "A whisper for Will");
  assert.equal(whisperHomeLabel({ memberName: "Will", unreadCount: 1 }), "A whisper for Will");
  assert.equal(whisperHomeLabel({ unreadCount: 0 }), "Whispers");
  assert.equal(whisperMemberName({ member_name: "Will" }), "Will");
  assert.equal(whisperWhy({ why: "Will, after Heat this one keeps that same mood." }).includes("Will"), true);
});

test("chat home opens the dedicated whisper route", () => {
  const workspaceJsx = readFileSync(new URL("../components/ChatWorkspace.jsx", import.meta.url), "utf8");
  const routesJsx = readFileSync(new URL("../AppRoutes.jsx", import.meta.url), "utf8");
  assert.match(workspaceJsx, /WhisperInboxLink/);
  assert.match(workspaceJsx, /<WhisperInboxLink/);
  assert.match(routesJsx, /path="\/whisper"/);
  assert.equal(WHISPER_PATH, "/whisper");
});
