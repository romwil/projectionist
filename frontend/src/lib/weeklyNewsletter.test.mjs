import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  newsletterConfirmMessage,
  newsletterResultMessage,
  NEWSLETTER_SCOPES,
} from "./weeklyNewsletter.js";

describe("weeklyNewsletter helpers", () => {
  it("exposes three scopes", () => {
    assert.equal(NEWSLETTER_SCOPES.length, 3);
    assert.deepEqual(
      NEWSLETTER_SCOPES.map((s) => s.value),
      ["self", "users", "all"],
    );
  });

  it("builds confirm copy per scope", () => {
    assert.match(newsletterConfirmMessage("self"), /opted in/i);
    assert.match(newsletterConfirmMessage("users", 1), /1 selected member/);
    assert.match(newsletterConfirmMessage("users", 3), /3 selected members/);
    assert.match(newsletterConfirmMessage("all"), /everyone who opted in/i);
  });

  it("summarizes delivery results", () => {
    assert.equal(
      newsletterResultMessage({ delivered: 1, emailed: 0, skipped_opt_out: 0 }),
      "Delivered to 1 inbox.",
    );
    assert.equal(
      newsletterResultMessage({ delivered: 2, emailed: 1, skipped_opt_out: 3 }),
      "Delivered to 2 inboxes · 1 emailed · 3 skipped (not opted in).",
    );
  });
});
