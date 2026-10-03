import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_QUEUE_PAD_DRAFT,
  QUEUE_PAD_UP_TO,
  queuePadDraft,
  queuePadDraftFromStation,
  queuePadPayload,
  queuePadSlots,
  queuePadSummary,
} from "./liveQueuePad.js";

test("slot math: 4 playing + up to 5 → 1 pad; 5 + 5 → 0; 0 + 3 → 3", () => {
  assert.equal(queuePadSlots(5, 4), 1);
  assert.equal(queuePadSlots(5, 5), 0);
  assert.equal(queuePadSlots(3, 0), 3);
  assert.equal(queuePadSlots(2, 9), 0);
});

test("up-to choices are 1 through 5 and the default is 5 / Recently added", () => {
  assert.deepEqual(QUEUE_PAD_UP_TO, [1, 2, 3, 4, 5]);
  assert.deepEqual(DEFAULT_QUEUE_PAD_DRAFT, { queue_up_to: 5, queue_feed: "recently_added" });
  assert.deepEqual(queuePadDraft({}), DEFAULT_QUEUE_PAD_DRAFT);
  assert.deepEqual(queuePadDraft({ queue_up_to: 9, queue_feed: "bogus" }), {
    queue_up_to: 5,
    queue_feed: "recently_added",
  });
});

test("payload is empty when padding is off, else up_to + feed", () => {
  assert.deepEqual(queuePadPayload({ queue_up_to: 0 }), {});
  assert.deepEqual(queuePadPayload({ queue_up_to: 3, queue_feed: "recently_released" }), {
    up_to: 3,
    feed: "recently_released",
  });
  assert.deepEqual(queuePadPayload(undefined), { up_to: 5, feed: "recently_added" });
});

test("a saved station with no padding reads as off", () => {
  assert.equal(queuePadDraftFromStation({}).queue_up_to, 0);
  assert.deepEqual(queuePadDraftFromStation({ queue_pad: { up_to: 4, feed: "recently_added" } }), {
    queue_up_to: 4,
    queue_feed: "recently_added",
  });
});

test("summary speaks plainly and never mentions the engine", () => {
  assert.match(queuePadSummary({ queue_up_to: 5, queue_feed: "recently_added" }, 4), /4 playing \+ 1 from recently added/);
  assert.match(queuePadSummary({ queue_up_to: 5 }, 5), /nothing to add/);
  assert.match(queuePadSummary({ queue_up_to: 0 }), /No padding/);
  assert.doesNotMatch(queuePadSummary({ queue_up_to: 3 }), /tunarr|engine/i);
});
