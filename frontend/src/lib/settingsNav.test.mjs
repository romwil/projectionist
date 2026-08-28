import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SETTINGS_NAV } from "./settingsNav.js";

describe("settingsNav", () => {
  it("uses descriptive settings rail labels (Wave 4 clarity)", () => {
    const labels = Object.fromEntries(SETTINGS_NAV.map((item) => [item.id, item.label]));
    assert.equal(labels.profile, "Profile");
    assert.equal(labels.voice, "Voice & persona");
    assert.equal(labels.taste, "Taste preferences");
    assert.equal(labels.notifications, "Notifications");
    assert.equal(labels.watchlist, "Watchlist");
    assert.equal(labels.lists, "Lists");
  });

  it("keeps stable settings nav test ids via route ids", () => {
    for (const item of SETTINGS_NAV) {
      assert.match(item.to, /^\/settings\//);
      assert.ok(item.id, `missing id for ${item.to}`);
    }
  });
});
