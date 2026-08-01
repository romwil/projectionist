import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";
import {
  LIVE_SOFT_STALL_PHRASES,
  pickLiveSoftStallPhrase,
  resetLiveSoftStallPhraseMemory,
} from "./liveStreamSoftStallCopy.js";

describe("liveStreamSoftStallCopy", () => {
  beforeEach(() => {
    resetLiveSoftStallPhraseMemory();
  });

  it("ships a living-room antenna library (not corporate buffering)", () => {
    assert.ok(LIVE_SOFT_STALL_PHRASES.length >= 12);
    assert.ok(LIVE_SOFT_STALL_PHRASES.some((p) => /antenna arms/i.test(p)));
    assert.ok(LIVE_SOFT_STALL_PHRASES.some((p) => /uhf antenna loop/i.test(p)));
    assert.ok(LIVE_SOFT_STALL_PHRASES.some((p) => /aluminum foil/i.test(p)));
    for (const phrase of LIVE_SOFT_STALL_PHRASES) {
      assert.doesNotMatch(phrase, /Buffering|Tunarr|hls\.js|HTTP \d/i);
      assert.match(phrase, /…$/);
    }
  });

  it("picks deterministically with an injected rng and avoids immediate repeats", () => {
    const phrases = ["one…", "two…", "three…"];
    const first = pickLiveSoftStallPhrase({ phrases, rng: () => 0 });
    assert.equal(first, "one…");
    const second = pickLiveSoftStallPhrase({ phrases, rng: () => 0 });
    assert.notEqual(second, first);
    const excluded = pickLiveSoftStallPhrase({
      phrases,
      rng: () => 0,
      exclude: "two…",
    });
    assert.notEqual(excluded, "two…");
  });
});
