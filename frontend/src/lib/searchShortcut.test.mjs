import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isSearchShortcut } from "./searchShortcut.ts";

describe("search shortcut", () => {
  it("accepts Ctrl+K and Command+K", () => {
    assert.equal(isSearchShortcut({ key: "k", ctrlKey: true }), true);
    assert.equal(isSearchShortcut({ key: "K", metaKey: true }), true);
  });

  it("ignores a plain K, Alt, and other chords", () => {
    assert.equal(isSearchShortcut({ key: "k" }), false);
    assert.equal(isSearchShortcut({ key: "k", ctrlKey: true, altKey: true }), false);
    assert.equal(isSearchShortcut({ key: "n", metaKey: true }), false);
    assert.equal(isSearchShortcut(null), false);
  });
});
