import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { approvalSentence } from "./sessionApprovalCopy.ts";

describe("approvalSentence", () => {
  it("names the ceiling and the title when approval would stop the room", () => {
    const line = approvalSentence({
      requester_name: "Sam",
      ceiling: "PG-13",
      title: "Heat",
      content_rating: "R",
      title_above: true,
    });
    assert.equal(
      line,
      "Sam wants to join. Approving limits this room to PG-13. Heat is rated R. Approving stops it.",
    );
  });

  it("leaves the title out when the film is already within the ceiling", () => {
    const line = approvalSentence({
      requester_name: "Sam",
      ceiling: "PG-13",
      title: "Wonder",
      content_rating: "G",
      title_above: false,
    });
    assert.equal(line, "Sam wants to join. Approving limits this room to PG-13.");
    assert.equal(line.includes("Wonder"), false);
  });
});
