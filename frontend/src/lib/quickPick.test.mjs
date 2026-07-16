import assert from "node:assert/strict";
import test from "node:test";

import {
  QUICK_PICK_EMPTY_MESSAGE,
  QUICK_PICK_ERROR_FALLBACK,
  normalizeQuickPickError,
  normalizeQuickPickResult,
} from "./quickPick.js";

test("normalizeQuickPickResult keeps a successful pick", () => {
  const item = { title: "Arrival", media_type: "movie", rating_key: "1" };
  const next = normalizeQuickPickResult({ item, why: "Unwatched pick for you" });
  assert.equal(next.status, "ready");
  assert.equal(next.item, item);
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
