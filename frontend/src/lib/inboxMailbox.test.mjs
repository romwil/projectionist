import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  INBOX_PAGE_SIZE,
  applyInboxDismiss,
  applyInboxRead,
  inboxAgentOutboundMessage,
  inboxFullMessage,
  inboxListParams,
  inboxPageSelection,
  inboxReplySubmission,
  inboxRowWhen,
  inboxScanPreview,
  inboxShowsListFilters,
  formatInboxWhen,
  isAgentInboxNote,
  visibleInboxReply,
} from "./inboxMailbox.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const longNote =
  "Jefferson put together a few notes for you. Gravity Falls still belongs on the shelf after Have I Got News for You.";

test("a row preview finishes a sentence and the open message keeps the stored note", () => {
  const item = {
    id: "weekly",
    kind: "digest",
    title: "This week for you",
    body: longNote,
    payload: { newsletter: "weekly", picks: [{ title: "Gravity Falls", tmdb_id: 1, media_type: "show" }] },
  };
  const preview = inboxScanPreview(longNote);
  assert.match(preview.text, /you\.$/);
  assert.equal(preview.continues, true);
  assert.equal(inboxFullMessage(item).body, longNote);
  assert.deepEqual(inboxFullMessage(item).titles, ["Gravity Falls"]);
  assert.notEqual(inboxFullMessage(item).body, preview.text);
});

test("a long sentence does not stop in the middle of a word", () => {
  const words = "Will after the news this still belongs on the shelf tonight with everyone";
  const preview = inboxScanPreview(words, { maxLen: 48 });
  assert.equal(preview.continues, true);
  assert.match(preview.text, /…$/);
  const cut = preview.text.slice(0, -1).trim();
  assert.ok(words.startsWith(cut));
  assert.equal(words[cut.length], " ");
});

test("reading keeps the row and dismiss removes it", () => {
  const items = [
    { id: "a", title: "One" },
    { id: "b", title: "Two" },
  ];
  const read = applyInboxRead(items, "a", 10);
  assert.equal(read.length, 2);
  assert.equal(read[0].read_at, 10);
  assert.equal(applyInboxDismiss(read, ["a"]).length, 1);
  assert.equal(applyInboxDismiss(read, ["a"])[0].id, "b");
});

test("the list can sort, filter unread, select the page, and page", () => {
  const params = inboxListParams({ status: "unread", sort: "oldest", page: 2 });
  assert.equal(params.status, "unread");
  assert.equal(params.sort, "oldest");
  assert.equal(params.limit, INBOX_PAGE_SIZE);
  assert.equal(params.offset, INBOX_PAGE_SIZE * 2);
  assert.ok(INBOX_PAGE_SIZE < 50);
  const page = [{ id: "a" }, { id: "b" }];
  assert.equal(inboxPageSelection(page, new Set(["a", "b"])).all, true);
  assert.equal(inboxPageSelection(page, new Set(["a"])).all, false);
});

test("opening an agent note has a composer and a reply stays on the inbox", () => {
  const note = readFileSync(join(root, "components/InboxNote.tsx"), "utf8");
  const page = readFileSync(join(root, "pages/InboxPage.tsx"), "utf8");
  assert.match(note, /data-testid="inbox-note-composer"/);
  assert.match(note, /inbox-message-body/);
  assert.doesNotMatch(note, /chatAboutTitleHref/);
  assert.doesNotMatch(note, /ROUTES\.chat/);
  assert.doesNotMatch(note, /\/chat/);
  assert.match(page, /sendChatStream/);
  assert.match(page, /createThread/);
  assert.doesNotMatch(page, /setActiveSession/);
  assert.equal(isAgentInboxNote({ kind: "digest", body: "notes" }), true);
  assert.equal(isAgentInboxNote({ kind: "nudge", payload: { enthusiast: true } }), false);
  assert.equal(isAgentInboxNote({ kind: "recommendation", title: "Worth a look" }), false);
  const submission = inboxReplySubmission();
  assert.equal(submission.stayOnInbox, true);
  assert.equal(submission.route, null);
});

test("a reply continues the same note instead of a blank chat", () => {
  const outbound = inboxAgentOutboundMessage("The week in films.", "What about Gravity Falls?", { first: true });
  assert.match(outbound, /The week in films\./);
  assert.match(outbound, /What about Gravity Falls\?/);
  assert.equal(visibleInboxReply(outbound), "What about Gravity Falls?");
  assert.equal(
    inboxAgentOutboundMessage("The week in films.", "And the other one?", { first: false }),
    "And the other one?",
  );
});

test("list filters stay on the inbox and leave the open letter", () => {
  assert.equal(inboxShowsListFilters(null), true);
  assert.equal(inboxShowsListFilters(undefined), true);
  assert.equal(inboxShowsListFilters({ id: "letter", title: "A letter about the house" }), false);
  const page = readFileSync(join(root, "pages/InboxPage.tsx"), "utf8");
  assert.match(page, /inboxShowsListFilters\(openItem\)/);
  assert.match(page, /showListFilters \? \(/);
  const toolbarStart = page.indexOf("showListFilters ? (");
  const toolbarEnd = page.indexOf(") : null}", toolbarStart);
  const toolbarBlock = page.slice(toolbarStart, toolbarEnd);
  assert.match(toolbarBlock, /className="inbox-toolbar"/);
  assert.match(toolbarBlock, /inbox-toolbar-controls/);
  assert.match(toolbarBlock, /data-testid="inbox-status"/);
  assert.match(toolbarBlock, /data-testid="inbox-sort"/);
  const afterToolbar = page.slice(toolbarEnd);
  assert.match(afterToolbar, /<InboxNote/);
  assert.doesNotMatch(afterToolbar, /inbox-status/);
  assert.doesNotMatch(afterToolbar, /inbox-sort/);
  assert.doesNotMatch(afterToolbar, /inbox-kind/);
});

test("a list row shows the same sent datetime as the open letter", () => {
  const createdAt = Date.UTC(2026, 9, 25, 21, 33) / 1000;
  const item = { id: "house", title: "A letter about the house", created_at: createdAt };
  const when = inboxRowWhen(item);
  assert.equal(when, formatInboxWhen(inboxFullMessage(item).when));
  assert.equal(when, formatInboxWhen(createdAt));
  assert.ok(when);
  assert.match(when, /2026/);
  assert.equal(inboxRowWhen({ id: "empty", title: "Note" }), "");
  assert.equal(inboxRowWhen({ id: "zero", created_at: 0 }), "");
  assert.equal(inboxRowWhen({ id: "null", created_at: null }), "");
  assert.equal(formatInboxWhen(""), "");
  const page = readFileSync(join(root, "pages/InboxPage.tsx"), "utf8");
  const note = readFileSync(join(root, "components/InboxNote.tsx"), "utf8");
  assert.match(page, /inboxRowWhen\(item\)/);
  assert.match(page, /inbox-row-when/);
  assert.match(note, /formatInboxWhen\(full\.when\)/);
  assert.match(note, /inbox-note-when/);
});
