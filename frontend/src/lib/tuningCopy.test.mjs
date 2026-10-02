import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";
import {
  TUNING_PHRASES,
  pickTuningPhrase,
  resetTuningPhraseMemory,
} from "./tuningCopy.js";

describe("tuningCopy", () => {
  beforeEach(() => {
    resetTuningPhraseMemory();
  });

  it("ships household-friendly adult-swim vibe lines", () => {
    assert.ok(TUNING_PHRASES.length >= 12);
    assert.ok(TUNING_PHRASES.some((p) => /rabbit ears/i.test(p)));
    assert.ok(TUNING_PHRASES.some((p) => /attic/i.test(p)));
    assert.ok(TUNING_PHRASES.some((p) => /neighbor/i.test(p)));
    for (const phrase of TUNING_PHRASES) {
      assert.doesNotMatch(phrase, /Buffering|Tunarr|hls\.js|HTTP \d|fuck|shit|damn/i);
      assert.ok(phrase.length < 80);
    }
  });

  it("picks deterministically and avoids immediate repeats", () => {
    const phrases = ["one", "two", "three"];
    const first = pickTuningPhrase({ phrases, rng: () => 0 });
    assert.equal(first, "one");
    const second = pickTuningPhrase({ phrases, rng: () => 0 });
    assert.notEqual(second, first);
  });
});
