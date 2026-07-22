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
  it("keeps secondary destinations in the drawer (peers live in the toolbar)", () => {
    const ids = buildAppNavItems().map((item) => item.id);
    assert.deepEqual(ids, [
      "plot-lab",
      "tags",
      "watchlist",
      "library",
      "my-journey",
      "help",
      "privacy",
      "about",
    ]);
  });

  it("does not duplicate Admin/Settings peers in the drawer", () => {
    const items = buildAppNavItems({ isOwner: true });
    const ids = items.map((item) => item.id);
    assert.equal(ids.includes("admin"), false);
    assert.equal(ids.includes("settings"), false);
    assert.equal(ids.includes("help"), true);
  });

  it("keeps core browse destinations stable", () => {
    assert.equal(APP_NAV_CORE_ITEMS.find((item) => item.id === "watchlist")?.kind, "watchlist");
    assert.equal(
      APP_NAV_CORE_ITEMS.find((item) => item.id === "my-journey")?.to,
      ROUTES.myJourney,
    );
  });

  it("uses a simplified youth nav without Badges-only entry", () => {
    const ids = buildAppNavItems({ isYouth: true, role: "member" }).map((item) => item.id);
    assert.deepEqual(ids.slice(0, YOUTH_NAV_ITEMS.length), YOUTH_NAV_ITEMS.map((i) => i.id));
    assert.equal(ids.includes("plot-lab"), false);
    assert.equal(ids.includes("admin"), false);
    assert.equal(ids.includes("my-journey"), true);
  });

  it("uses a guest tour nav", () => {
    const ids = buildAppNavItems({ role: "guest" }).map((item) => item.id);
    assert.equal(ids[0], "tour");
    assert.deepEqual(ids.slice(0, GUEST_NAV_ITEMS.length), GUEST_NAV_ITEMS.map((i) => i.id));
    assert.equal(ids.includes("settings"), false);
  });
});
