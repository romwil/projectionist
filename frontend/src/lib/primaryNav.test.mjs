import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import {
  PRIMARY_NAV_ITEMS,
  buildPrimaryDrawerItems,
  buildPrimaryNavItems,
  isPrimaryNavActive,
  primaryNavVisibleIds,
} from "./primaryNav.js";

describe("primaryNav", () => {
  it("orders peers Search → Chat → Explore → Inbox → Admin → My Journey → Settings", () => {
    assert.deepEqual(
      PRIMARY_NAV_ITEMS.map((item) => item.id),
      ["search", "chat", "explore", "inbox", "admin", "my-journey", "settings"],
    );
    const owner = buildPrimaryNavItems({ role: "owner", isOwner: true });
    assert.deepEqual(
      owner.map((item) => item.id),
      ["search", "chat", "explore", "inbox", "admin", "my-journey", "settings"],
    );
    assert.equal(owner.at(-2).id, "my-journey");
    assert.equal(owner.at(-1).id, "settings");
  });

  it("hides Admin for members and places My Journey left of Settings", () => {
    const ids = primaryNavVisibleIds({ role: "member", isOwner: false });
    assert.deepEqual(ids, ["search", "chat", "explore", "inbox", "my-journey", "settings"]);
  });

  it("never includes Admin while auth is unresolved even if isOwner defaults true", () => {
    const unresolved = primaryNavVisibleIds({
      role: "owner",
      isOwner: true,
      multiUserEnabled: true,
      authReady: false,
    });
    assert.deepEqual(unresolved, []);
    assert.equal(unresolved.includes("admin"), false);

    const memberAfterReady = primaryNavVisibleIds({
      role: "member",
      isOwner: false,
      multiUserEnabled: true,
      authReady: true,
    });
    assert.equal(memberAfterReady.includes("admin"), false);
    assert.deepEqual(memberAfterReady, [
      "search",
      "chat",
      "explore",
      "inbox",
      "my-journey",
      "settings",
    ]);

    const itemsUnresolved = buildPrimaryNavItems({
      role: "owner",
      isOwner: true,
      authReady: false,
    });
    assert.equal(itemsUnresolved.some((item) => item.id === "admin"), false);
  });

  it("youth sees Ask/Browse labels and My Journey, never Admin", () => {
    const items = buildPrimaryNavItems({
      role: "member",
      isOwner: false,
      isYouth: true,
    });
    assert.equal(items.find((i) => i.id === "chat")?.label, "Ask");
    assert.equal(items.find((i) => i.id === "explore")?.label, "Browse");
    assert.equal(items.some((i) => i.id === "admin"), false);
    assert.equal(items.some((i) => i.id === "my-journey"), true);
  });

  it("guest sees only Search, Chat, Explore", () => {
    assert.deepEqual(primaryNavVisibleIds({ role: "guest" }), [
      "search",
      "chat",
      "explore",
    ]);
  });

  it("shapes the same peers for the drawer with app-nav test ids", () => {
    const owner = buildPrimaryDrawerItems({ role: "owner", isOwner: true });
    assert.deepEqual(
      owner.map((item) => item.id),
      buildPrimaryNavItems({ role: "owner", isOwner: true }).map((item) => item.id),
    );
    assert.deepEqual(
      owner.map((item) => item.testId),
      [
        "app-nav-search",
        "app-nav-chat",
        "app-nav-explore",
        "app-nav-inbox",
        "app-nav-admin",
        "app-nav-my-journey",
        "app-nav-settings",
      ],
    );
    assert.ok(owner.every((item) => item.kind === "primary" && item.label && item.to));
    assert.deepEqual(buildPrimaryDrawerItems({ isOwner: true, authReady: false }), []);
  });

  it("marks chat active for /chat", () => {
    assert.equal(
      isPrimaryNavActive({ id: "chat", to: ROUTES.chat }, ROUTES.chat),
      true,
    );
    assert.equal(
      isPrimaryNavActive({ id: "search", to: ROUTES.search }, ROUTES.search),
      true,
    );
  });
});
