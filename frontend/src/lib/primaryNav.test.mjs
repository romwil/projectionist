import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import {
  PRIMARY_NAV_ITEMS,
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
