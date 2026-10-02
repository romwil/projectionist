import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isPauseBoundaryDismissed,
  pauseBoundaryForPlaybackStatus,
  pauseBoundaryOnPauseGesture,
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

  it("suppresses Rejoin/Finish only until playback resumes or the next pause", () => {
    const dismissed = { open: false };
    const open = { open: true };

    assert.equal(isPauseBoundaryDismissed(dismissed), true);
    assert.equal(isPauseBoundaryDismissed(open), false);
    assert.equal(isPauseBoundaryDismissed(null), false);
    assert.equal(isPauseBoundaryDismissed(undefined), false);
    assert.equal(isPauseBoundaryDismissed({}), false);
    assert.equal(isPauseBoundaryDismissed({ open: true, extra: 1 }), false);

    // Still paused inside the old boundary — do not reopen.
    assert.equal(pauseBoundaryForPlaybackStatus(dismissed, "paused"), dismissed);
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: true,
        programEndsAtSec: 100,
        nowSec: 200,
        dismissed: isPauseBoundaryDismissed(
          pauseBoundaryForPlaybackStatus(dismissed, "paused"),
        ),
      }),
      false,
    );

    // Playback resumed — dismissal is gone, so the next pause can prompt.
    assert.equal(pauseBoundaryForPlaybackStatus(dismissed, "playing"), null);
    assert.equal(pauseBoundaryForPlaybackStatus(dismissed, "loading"), null);
    assert.equal(pauseBoundaryForPlaybackStatus(open, "playing"), open);
    assert.equal(pauseBoundaryForPlaybackStatus(null, "playing"), null);
    const afterResume = pauseBoundaryForPlaybackStatus(dismissed, "playing");
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: true,
        programEndsAtSec: 100,
        nowSec: 200,
        dismissed: isPauseBoundaryDismissed(afterResume),
      }),
      true,
    );

    // A later pause gesture also drops a leftover dismissal before arming.
    assert.equal(pauseBoundaryOnPauseGesture(dismissed), null);
    assert.equal(pauseBoundaryOnPauseGesture(null), null);
    assert.equal(pauseBoundaryOnPauseGesture(open), open);
    const afterGesture = pauseBoundaryOnPauseGesture(dismissed);
    assert.equal(
      shouldPromptPausePastBoundary({
        paused: true,
        programEndsAtSec: 50,
        nowSec: 80,
        dismissed: isPauseBoundaryDismissed(afterGesture),
      }),
      true,
    );
  });

  it("reads program end from OSD ends_at or remaining", () => {
    assert.equal(programEndSecFromOsd({ ends_at: 500 }), 500);
    assert.equal(programEndSecFromOsd({ stop: 600 }), 600);
    assert.equal(programEndSecFromOsd({ secondsRemaining: 30 }, 1000), 1030);
    assert.equal(programEndSecFromOsd(null), null);
  });
});
