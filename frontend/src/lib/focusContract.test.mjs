import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isDialogDismissKey,
  isFocusable,
  isTabKey,
  nextFocusTrapIndex,
} from "./focusContract.ts";

describe("focusContract", () => {
  it("isFocusable rejects disabled, negative-tabindex, and aria-hidden elements", () => {
    assert.equal(isFocusable(null), false);
    assert.equal(isFocusable({ disabled: true }), false);
    assert.equal(isFocusable({ tabIndex: -1 }), false);
    assert.equal(
      isFocusable({ getAttribute: (name) => (name === "aria-hidden" ? "true" : null) }),
      false,
    );
    assert.equal(isFocusable({ tabIndex: 0 }), true);
    assert.equal(isFocusable({}), true);
  });

  it("nextFocusTrapIndex wraps forward and backward", () => {
    assert.equal(nextFocusTrapIndex(3, -1), 0, "no current focus → first item");
    assert.equal(nextFocusTrapIndex(3, -1, { shiftKey: true }), 2, "shift+tab from outside → last item");
    assert.equal(nextFocusTrapIndex(3, 0), 1);
    assert.equal(nextFocusTrapIndex(3, 1), 2);
    assert.equal(nextFocusTrapIndex(3, 2), 0, "forward wraps to first");
    assert.equal(nextFocusTrapIndex(3, 0, { shiftKey: true }), 2, "backward wraps to last");
    assert.equal(nextFocusTrapIndex(0, -1), -1, "empty trap has no target");
  });

  it("isDialogDismissKey only fires Escape, and never while busy", () => {
    assert.equal(isDialogDismissKey({ key: "Escape" }), true);
    assert.equal(isDialogDismissKey({ key: "Escape" }, { busy: true }), false);
    assert.equal(isDialogDismissKey({ key: "Enter" }), false);
    assert.equal(isDialogDismissKey(null), false);
  });

  it("isTabKey recognizes only Tab", () => {
    assert.equal(isTabKey({ key: "Tab" }), true);
    assert.equal(isTabKey({ key: "a" }), false);
    assert.equal(isTabKey(null), false);
  });
});
