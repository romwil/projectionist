import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { COMPOSER_IDLE_PLACEHOLDER, COMPOSER_OPENING_LINE, composerStatus } from "./composerStatus.ts";
import { findMainLandmark } from "./skipLink.ts";

function fakeRoot({ byId = null, first = null } = {}) {
  return {
    getElementById: (id) => (id === "main" ? byId : null),
    querySelector: () => first,
  };
}

describe("findMainLandmark (A11Y-008)", () => {
  it("prefers #main", () => {
    const byId = { id: "main" };
    assert.equal(findMainLandmark(fakeRoot({ byId, first: { id: "other" } })), byId);
  });

  it("falls back to the page's own main", () => {
    const first = { tagName: "MAIN" };
    assert.equal(findMainLandmark(fakeRoot({ first })), first);
  });

  it("returns null when the page has no landmark", () => {
    assert.equal(findMainLandmark(fakeRoot()), null);
    assert.equal(findMainLandmark(null), null);
  });
});

describe("composerStatus (A11Y-009)", () => {
  it("says the library is opening instead of inviting typing", () => {
    const state = composerStatus({ ready: false, placeholder: "Ask anything" });
    assert.equal(state.placeholder, COMPOSER_OPENING_LINE);
    assert.equal(state.statusLine, COMPOSER_OPENING_LINE);
  });

  it("is silent and inviting once ready", () => {
    assert.deepEqual(composerStatus({ ready: true }), {
      placeholder: COMPOSER_IDLE_PLACEHOLDER,
      statusLine: "",
    });
    assert.equal(composerStatus({ ready: true, placeholder: "Ask Ada" }).placeholder, "Ask Ada");
    assert.equal(composerStatus({ ready: true, listening: true }).placeholder, "Listening…");
  });
});
