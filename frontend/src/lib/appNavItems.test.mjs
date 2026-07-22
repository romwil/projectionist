import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import {
  APP_NAV_CORE_ITEMS,
  GUEST_NAV_ITEMS,
  YOUTH_NAV_ITEMS,
  buildAppNavItems,
} from "./appNavItems.js";

describe("buildAppNavItems", () => {
  it("includes chat, explore family, library, and footer destinations", () => {
    const ids = buildAppNavItems().map((item) => item.id);
    assert.deepEqual(ids, [
      "chat",
      "explore",
      "plot-lab",
      "tags",
      "watchlist",
      "library",
      "settings",
      "help",
      "privacy",
      "about",
    ]);
  });

  it("adds Admin for owners and keeps Help · Privacy · About", () => {
    const items = buildAppNavItems({ isOwner: true });
    const byId = Object.fromEntries(items.map((item) => [item.id, item]));
    assert.equal(byId.admin.to, ROUTES.admin);
    assert.equal(byId.help.to, ROUTES.help);
    assert.equal(byId.privacy.to, ROUTES.privacy);
    assert.equal(byId.about.to, ROUTES.about);
  });

  it("can omit Settings when requested", () => {
    const ids = buildAppNavItems({ showSettings: false }).map((item) => item.id);
    assert.equal(ids.includes("settings"), false);
    assert.equal(ids.includes("help"), true);
  });

  it("keeps core browse destinations stable", () => {
    assert.equal(APP_NAV_CORE_ITEMS[0].to, ROUTES.chat);
    assert.equal(APP_NAV_CORE_ITEMS.find((item) => item.id === "watchlist")?.kind, "watchlist");
  });

  it("uses a simplified youth nav", () => {
    const ids = buildAppNavItems({ isYouth: true, role: "member" }).map((item) => item.id);
    assert.deepEqual(ids.slice(0, YOUTH_NAV_ITEMS.length), YOUTH_NAV_ITEMS.map((i) => i.id));
    assert.equal(ids.includes("plot-lab"), false);
    assert.equal(ids.includes("admin"), false);
  });

  it("uses a guest tour nav", () => {
    const ids = buildAppNavItems({ role: "guest" }).map((item) => item.id);
    assert.equal(ids[0], "tour");
    assert.deepEqual(ids.slice(0, GUEST_NAV_ITEMS.length), GUEST_NAV_ITEMS.map((i) => i.id));
    assert.equal(ids.includes("settings"), false);
  });
});
