import assert from "node:assert/strict";
import test from "node:test";

import { formatPublishFeedback } from "./liveChannelsPublishFeedback.ts";

test("formatPublishFeedback summarizes a clean publish", () => {
  const feedback = formatPublishFeedback({
    ok: true,
    count_published: 2,
    count_skipped: 0,
    count_errors: 0,
    lineup_programs: 14,
  });
  assert.equal(feedback.type, "success");
  assert.match(feedback.summary, /Published 2/);
  assert.match(feedback.summary, /lineup 14 programs/);
  assert.equal(feedback.details.length, 0);
});

test("formatPublishFeedback omits zero skip/error counts", () => {
  const feedback = formatPublishFeedback({
    count_published: 1,
    count_skipped: 0,
    count_errors: 0,
  });
  assert.doesNotMatch(feedback.summary, /skipped/);
  assert.doesNotMatch(feedback.summary, /errors/);
});

test("formatPublishFeedback surfaces errors as type error", () => {
  const feedback = formatPublishFeedback({
    ok: false,
    count_published: 0,
    count_errors: 1,
    errors: [{ number: 101, name: "Noir", error: "empty lineup" }],
  });
  assert.equal(feedback.type, "error");
  assert.match(feedback.summary, /errors 1/);
  assert.equal(feedback.details[0], "101 · Noir: empty lineup");
});
