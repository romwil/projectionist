import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  programEndSecFromOsd,
  shouldPromptPausePastBoundary,
} from "./livePauseBoundary.js";

describe("livePauseBoundary", () => {
  it("prompts only when paused past program end and not dismissed", () => {
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: true,
        programEndsAtSec: 100,
        nowSec: 100,
      }),
      true,
    );
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: true,
        programEndsAtSec: 100,
        nowSec: 99,
      }),
      false,
    );
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: false,
        programEndsAtSec: 100,
        nowSec: 200,
      }),
      false,
    );
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: true,
        programEndsAtSec: 100,
        nowSec: 200,
        dismissed: true,
      }),
      false,
    );
  });

  it("reads program end from OSD ends_at or remaining", () => {
    assert.equal(programEndSecFromOsd({ ends_at: 500 }), 500);
    assert.equal(programEndSecFromOsd({ stop: 600 }), 600);
    assert.equal(programEndSecFromOsd({ secondsRemaining: 30 }, 1000), 1030);
    assert.equal(programEndSecFromOsd(null), null);
  });
});
