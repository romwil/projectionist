import assert from "node:assert/strict";
import test from "node:test";
import { normalizeUiFontSize } from "./uiPrefs.js";

test("normalizeUiFontSize accepts small medium large", () => {
  assert.equal(normalizeUiFontSize("small"), "small");
  assert.equal(normalizeUiFontSize("medium"), "medium");
  assert.equal(normalizeUiFontSize("large"), "large");
});

test("normalizeUiFontSize defaults invalid values to medium", () => {
  assert.equal(normalizeUiFontSize("huge"), "medium");
  assert.equal(normalizeUiFontSize(null), "medium");
  assert.equal(normalizeUiFontSize(undefined), "medium");
});
