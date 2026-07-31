import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { liveChannelsStartTimeoutAlertType } from "./liveChannelsEngineFeedback.js";

describe("liveChannelsStartTimeoutAlertType", () => {
  it("uses success for still-starting (soft / in-progress)", () => {
    assert.equal(liveChannelsStartTimeoutAlertType(true), "success");
  });

  it("uses error for a real timeout", () => {
    assert.equal(liveChannelsStartTimeoutAlertType(false), "error");
  });
});
