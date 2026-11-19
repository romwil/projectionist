import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveDefaultHome } from "./defaultHome.ts";

describe("resolveDefaultHome (EXP-013)", () => {
  it("defaults to explore when unset, including when an LLM is configured", () => {
    assert.equal(resolveDefaultHome({ defaultPage: "auto", llmConfigured: true }), "/explore");
    assert.equal(resolveDefaultHome({}), "/explore");
    assert.equal(resolveDefaultHome({ llmConfigured: true }), "/explore");
  });

  it("defaults to explore when unset and no LLM is configured", () => {
    assert.equal(resolveDefaultHome({ defaultPage: "auto", llmConfigured: false }), "/explore");
    assert.equal(resolveDefaultHome({ llmConfigured: false }), "/explore");
  });

  it("honors an explicit chat preference even without an LLM", () => {
    assert.equal(resolveDefaultHome({ defaultPage: "chat", llmConfigured: false }), "/chat");
  });

  it("honors an explicit explore preference even with an LLM configured", () => {
    assert.equal(resolveDefaultHome({ defaultPage: "explore", llmConfigured: true }), "/explore");
  });

  it("treats unknown values as explore", () => {
    assert.equal(resolveDefaultHome({ defaultPage: "nonsense", llmConfigured: true }), "/explore");
    assert.equal(resolveDefaultHome({ defaultPage: "nonsense", llmConfigured: false }), "/explore");
  });
});
