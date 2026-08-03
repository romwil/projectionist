import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CURATOR_CAPABILITIES,
  curatorCapabilitiesIntro,
  curatorCapabilityLabels,
} from "./curatorCapabilities.js";

describe("curatorCapabilities", () => {
  it("lists product-facing capabilities without raw tool names", () => {
    const labels = curatorCapabilityLabels();
    assert.ok(labels.length >= 8);
    const joined = labels.join(" ").toLowerCase();
    for (const token of [
      "search_library",
      "mark_bad_media",
      "consult_persona",
      "confirm_pending_action",
      "build_tool_definitions",
    ]) {
      assert.ok(!joined.includes(token), `should not expose tool id ${token}`);
    }
  });

  it("covers acquisition, village, and bad-media semantics", () => {
    const ids = new Set(CURATOR_CAPABILITIES.map((row) => row.id));
    assert.ok(ids.has("acquire"));
    assert.ok(ids.has("village"));
    assert.ok(ids.has("bad-media"));
  });

  it("uses member-friendly browse terminology", () => {
    const explore = CURATOR_CAPABILITIES.find((row) => row.id === "explore");
    assert.match(explore.label, /tags & genres/i);
    assert.doesNotMatch(explore.label, /facets/i);
  });

  it("intro discourages prompt surgery", () => {
    const intro = curatorCapabilitiesIntro();
    assert.match(intro, /not editable/i);
    assert.match(intro, /voice and tone/i);
  });
});
