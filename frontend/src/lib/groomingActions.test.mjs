import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  canUndoGroomingAction,
  formatGroomingActionLine,
  formatUndoSuccess,
  groomingActionStatusLabel,
} from "./groomingActions.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const styles = readFileSync(join(root, "styles.css"), "utf8");

describe("canUndoGroomingAction", () => {
  it("is true for a fresh action with items", () => {
    assert.equal(canUndoGroomingAction({ item_count: 3, undone_at: null }), true);
  });
  it("is false once undone or empty", () => {
    assert.equal(canUndoGroomingAction({ item_count: 3, undone_at: 100 }), false);
    assert.equal(canUndoGroomingAction({ item_count: 0, undone_at: null }), false);
    assert.equal(canUndoGroomingAction(null), false);
  });
});

describe("groomingActionStatusLabel", () => {
  it("labels undoable, undone, and non-reversible", () => {
    assert.equal(groomingActionStatusLabel({ item_count: 2, undone_at: null }), "Undoable");
    assert.equal(groomingActionStatusLabel({ item_count: 2, undone_at: 5 }), "Undone");
    assert.equal(groomingActionStatusLabel({ item_count: 0, undone_at: null }), "Not reversible");
  });
});

describe("formatGroomingActionLine / formatUndoSuccess", () => {
  it("keeps the summary and appends a timestamp when present", () => {
    const line = formatGroomingActionLine({ summary: "Deleted 2 purge candidates", created_at: 0 });
    assert.match(line, /Deleted 2 purge candidates/);
    assert.equal(formatGroomingActionLine({ summary: "x" }), "x");
    assert.equal(formatGroomingActionLine(null), "");
  });
  it("counts restored titles with correct pluralization", () => {
    assert.equal(formatUndoSuccess({ restored: 1 }), "Restored 1 title to the library index.");
    assert.equal(formatUndoSuccess({ restored: 3 }), "Restored 3 titles to the library index.");
    assert.equal(formatUndoSuccess({}), "Restored 0 titles to the library index.");
  });
});

describe("grooming undo theme-safe styles", () => {
  it("defines grooming panel styles", () => {
    assert.match(styles, /\.grooming-panel\b/);
    assert.match(styles, /\.grooming-action-row\b/);
  });
});
