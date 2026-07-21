import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import {
  computeReorder,
  formatCollectionStepTitle,
  isPublished,
  orderCollectionSteps,
} from "./collections.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const styles = readFileSync(join(root, "styles.css"), "utf8");

describe("orderCollectionSteps", () => {
  it("orders by position then created_at", () => {
    const ordered = orderCollectionSteps([
      { id: "c", position: 2, created_at: 1 },
      { id: "a", position: 0, created_at: 5 },
      { id: "b", position: 0, created_at: 2 },
    ]);
    assert.deepEqual(
      ordered.map((i) => i.id),
      ["b", "a", "c"],
    );
  });
});

describe("formatCollectionStepTitle / isPublished", () => {
  it("formats title with year", () => {
    assert.equal(formatCollectionStepTitle({ title: "Ran", year: 1985 }), "Ran (1985)");
    assert.equal(formatCollectionStepTitle({ title: "X" }), "X");
  });
  it("detects published visibility", () => {
    assert.equal(isPublished({ visibility: "published" }), true);
    assert.equal(isPublished({ visibility: "private" }), false);
    assert.equal(isPublished(null), false);
  });
});

describe("computeReorder", () => {
  const items = [
    { id: "a", position: 0 },
    { id: "b", position: 1 },
    { id: "c", position: 2 },
  ];
  it("swaps adjacent positions moving up", () => {
    const updates = computeReorder(items, "b", "up");
    assert.deepEqual(updates, [
      { id: "b", position: 0 },
      { id: "a", position: 1 },
    ]);
  });
  it("swaps adjacent positions moving down", () => {
    const updates = computeReorder(items, "b", "down");
    assert.deepEqual(updates, [
      { id: "b", position: 2 },
      { id: "c", position: 1 },
    ]);
  });
  it("is a no-op at the edges or for unknown id", () => {
    assert.deepEqual(computeReorder(items, "a", "up"), []);
    assert.deepEqual(computeReorder(items, "c", "down"), []);
    assert.deepEqual(computeReorder(items, "zzz", "up"), []);
  });
});

describe("collections theme-safe styles", () => {
  it("defines collection step + visibility styles", () => {
    assert.match(styles, /\.collection-step\b/);
    assert.match(styles, /\.collection-visibility\.is-published\b/);
    assert.match(styles, /\.youth-review\b/);
  });
});
