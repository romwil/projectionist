import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  HEALTH_TABS,
  healthTabHref,
  legacyHealthTabFromPath,
  resolveHealthTab,
} from "./healthTabs.js";

describe("healthTabs", () => {
  it("defaults to sync health tab", () => {
    assert.equal(resolveHealthTab(null), "sync");
    assert.equal(resolveHealthTab(""), "sync");
    assert.equal(resolveHealthTab("bogus"), "sync");
  });

  it("resolves known tab ids", () => {
    for (const tab of HEALTH_TABS) {
      assert.equal(resolveHealthTab(tab.id), tab.id);
    }
  });

  it("builds canonical health hrefs", () => {
    assert.equal(healthTabHref("sync"), "/admin/health");
    assert.equal(healthTabHref("usage"), "/admin/health?tab=usage");
    assert.equal(healthTabHref("issues"), "/admin/health?tab=issues");
  });

  it("maps legacy admin paths to tab ids", () => {
    assert.equal(legacyHealthTabFromPath("/admin/dashboard"), "sync");
    assert.equal(legacyHealthTabFromPath("/admin/usage"), "usage");
    assert.equal(legacyHealthTabFromPath("/admin/issues"), "issues");
    assert.equal(legacyHealthTabFromPath("/admin/health"), null);
  });
});
