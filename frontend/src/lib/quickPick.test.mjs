import assert from "node:assert/strict";
import test from "node:test";

import {
  QUICK_PICK_EMPTY_MESSAGE,
  QUICK_PICK_ERROR_FALLBACK,
  normalizeQuickPickError,
  normalizeQuickPickGenres,
  normalizeQuickPickResult,
  quickPickToAssistantMessage,
} from "./quickPick.js";

test("normalizeQuickPickResult keeps a successful pick", () => {
  const item = { title: "Arrival", media_type: "movie", rating_key: "1" };
  const next = normalizeQuickPickResult({ item, why: "Unwatched pick for you" });
  assert.equal(next.status, "ready");
  assert.equal(next.item.title, "Arrival");
  assert.equal(next.item.rating_key, "1");
  assert.equal(next.item.in_library, true);
  assert.deepEqual(next.item.genres, []);
  assert.equal(next.why, "Unwatched pick for you");
  assert.equal(next.message, null);
});

test("normalizeQuickPickResult surfaces empty API responses instead of no-op", () => {
  const next = normalizeQuickPickResult({
    item: null,
    why: "No unwatched titles match the criteria.",
  });
  assert.equal(next.status, "empty");
  assert.equal(next.item, null);
  assert.equal(next.message, "No unwatched titles match the criteria.");
});

test("normalizeQuickPickResult uses fallback empty copy when why is missing", () => {
  const next = normalizeQuickPickResult({ item: null });
  assert.equal(next.status, "empty");
  assert.equal(next.message, QUICK_PICK_EMPTY_MESSAGE);
});

test("normalizeQuickPickResult treats missing payload as empty", () => {
  const next = normalizeQuickPickResult(null);
  assert.equal(next.status, "empty");
  assert.equal(next.item, null);
  assert.equal(next.message, QUICK_PICK_EMPTY_MESSAGE);
});

test("normalizeQuickPickError surfaces API failures", () => {
  const next = normalizeQuickPickError(new Error("Library unavailable"), (err) => err.message);
  assert.equal(next.status, "error");
  assert.equal(next.item, null);
  assert.equal(next.message, "Library unavailable");
});

test("normalizeQuickPickError falls back when formatter returns blank", () => {
  const next = normalizeQuickPickError({}, () => "  ");
  assert.equal(next.status, "error");
  assert.equal(next.message, QUICK_PICK_ERROR_FALLBACK);
});

test("normalizeQuickPickResult maps summary to overview and marks in_library", () => {
  const next = normalizeQuickPickResult({
    item: { title: "Arrival", media_type: "movie", summary: "Linguists meet aliens.", genres: ["Sci-Fi"] },
    why: "Unwatched pick for you",
  });
  assert.equal(next.status, "ready");
  assert.equal(next.item.overview, "Linguists meet aliens.");
  assert.equal(next.item.in_library, true);
  assert.deepEqual(next.item.genres, ["Sci-Fi"]);
});

test("normalizeQuickPickResult coerces genres JSON string for TitleCard safety", () => {
  const next = normalizeQuickPickResult({
    item: { title: "Broken", genres: '["Horror","Thriller"]' },
  });
  assert.deepEqual(next.item.genres, ["Horror", "Thriller"]);
});

test("normalizeQuickPickGenres returns empty array for malformed JSON", () => {
  assert.deepEqual(normalizeQuickPickGenres("not-json"), []);
  assert.deepEqual(normalizeQuickPickGenres(null), []);
});

test("quickPickToAssistantMessage renders a compact title-card block followed by its why", () => {
  const pick = normalizeQuickPickResult({
    item: { title: "Arrival", media_type: "movie", rating_key: "1" },
    why: "A thoughtful first-contact mystery for tonight.",
  });

  assert.deepEqual(quickPickToAssistantMessage(pick), {
    role: "assistant",
    blocks: [
      { type: "title_cards", items: [pick.item] },
      { type: "text", content: "A thoughtful first-contact mystery for tonight." },
    ],
  });
});

test("quickPickToAssistantMessage gives empty and failed picks a clear agent reply", () => {
  assert.deepEqual(quickPickToAssistantMessage({
    status: "empty",
    item: null,
    message: "Nothing unwatched fits.",
  }), {
    role: "assistant",
    blocks: [{ type: "text", content: "Nothing unwatched fits." }],
  });
});
