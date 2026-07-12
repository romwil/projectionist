import assert from "node:assert/strict";
import test from "node:test";

import { shouldSubmitComposerOnEnter } from "./composerKeyboard.js";

function keyEvent(overrides = {}) {
  return {
    key: "Enter",
    shiftKey: false,
    isComposing: false,
    keyCode: 13,
    ...overrides,
  };
}

test("Enter submits when canSubmit is true", () => {
  assert.equal(shouldSubmitComposerOnEnter(keyEvent(), { canSubmit: true }), true);
});

test("Enter does not submit when empty or sending", () => {
  assert.equal(shouldSubmitComposerOnEnter(keyEvent(), { canSubmit: false }), false);
});

test("Shift+Enter does not submit", () => {
  assert.equal(shouldSubmitComposerOnEnter(keyEvent({ shiftKey: true }), { canSubmit: true }), false);
});

test("non-Enter keys do not submit", () => {
  assert.equal(shouldSubmitComposerOnEnter(keyEvent({ key: "a" }), { canSubmit: true }), false);
});

test("IME composition does not submit", () => {
  assert.equal(shouldSubmitComposerOnEnter(keyEvent({ isComposing: true }), { canSubmit: true }), false);
  assert.equal(shouldSubmitComposerOnEnter(keyEvent({ keyCode: 229 }), { canSubmit: true }), false);
});
