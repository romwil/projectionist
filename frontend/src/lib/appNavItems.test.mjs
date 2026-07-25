import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import {
  APP_NAV_CORE_ITEMS,
  GUEST_NAV_ITEMS,
  YOUTH_NAV_ITEMS,
  buildAppNavItems,
} from "./appNavItems.js";
import { ADMIN_NAV } from "./adminNav.js";

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

  it("does not dump Admin section links into the drawer outside /admin", () => {
    const items = buildAppNavItems({ isOwner: true, pathname: "/chat" });
    const ids = items.map((item) => item.id);
    assert.equal(ids.includes("admin"), false);
    assert.equal(ids.includes("heading-admin"), false);
    assert.equal(ids.includes("admin-overview"), false);
    assert.equal(ids.includes("settings"), false);
    assert.equal(ids.includes("help"), true);
  });

  it("prepends Admin section links when owner is on /admin/*", () => {
    const items = buildAppNavItems({
      isOwner: true,
      pathname: "/admin/overview",
    });
    const ids = items.map((item) => item.id);
    assert.equal(ids[0], "heading-admin");
    assert.equal(ids[1], "admin-overview");
    assert.ok(ids.includes("admin-issues"));
    assert.ok(ids.includes("heading-more"));
    const moreIdx = ids.indexOf("heading-more");
    assert.deepEqual(ids.slice(moreIdx + 1), [
      "plot-lab",
      "tags",
      "watchlist",
      "library",
      "my-journey",
      "help",
      "privacy",
      "about",
    ]);
    assert.equal(
      items.filter((item) => item.kind === "admin").length,
      ADMIN_NAV.length,
    );
  });

  it("does not prepend Admin section for non-owners on /admin paths", () => {
    const ids = buildAppNavItems({
      isOwner: false,
      role: "member",
      pathname: "/admin/overview",
    }).map((item) => item.id);
    assert.equal(ids.includes("heading-admin"), false);
    assert.equal(ids.includes("admin-overview"), false);
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
