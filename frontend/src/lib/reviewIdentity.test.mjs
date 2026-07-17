import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatRateBatchLead,
  formatRateTitleLead,
  resolveReviewAddressName,
  resolveReviewUser,
} from "./reviewIdentity.js";

describe("reviewIdentity", () => {
  it("prefers preferred_name over display_name", () => {
    assert.equal(
      resolveReviewAddressName({ preferred_name: "Will", display_name: "wrompala" }),
      "Will",
    );
  });

  it("falls back to display_name then null", () => {
    assert.equal(resolveReviewAddressName({ display_name: "Will" }), "Will");
    assert.equal(resolveReviewAddressName({ preferred_name: "  ", display_name: "" }), null);
    assert.equal(resolveReviewAddressName(null), null);
  });

  it("formats rate leads with user name or neutral copy (never agent name)", () => {
    assert.match(formatRateBatchLead("Will"), /^Will —/);
    assert.match(formatRateBatchLead(null), /^Rate what you've watched/);
    assert.doesNotMatch(formatRateBatchLead(null), /Jefferson|Curator/);
    assert.match(formatRateTitleLead("Will", "Heat"), /Will — quick take on \*\*Heat\*\*/);
    assert.equal(formatRateTitleLead("", "Heat"), "Quick take on **Heat**?");
  });

  it("resolveReviewUser prefers auth profile over features fallback", () => {
    assert.equal(
      resolveReviewUser(
        { preferred_name: "Will" },
        { display_name: "romwill" },
      ),
      "Will",
    );
    assert.equal(resolveReviewUser(null, { display_name: "romwill" }), "romwill");
    assert.equal(resolveReviewUser(null, null), null);
  });
});
