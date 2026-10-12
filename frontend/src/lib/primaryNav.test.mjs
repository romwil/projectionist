import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import { initialLiveChannelsReady, LIVE_NAV_READY_KEY } from "./liveNavReady.js";
import {
  PRIMARY_NAV_ITEMS,
  buildPrimaryDrawerItems,
  buildPrimaryNavItems,
  isPrimaryNavActive,
  primaryNavVisibleIds,
} from "./primaryNav.js";

describe("primaryNav", () => {
  it("orders peers Search → Chat → Explore → Live → Inbox → Admin → My Journey → Settings", () => {
    assert.deepEqual(
      PRIMARY_NAV_ITEMS.map((item) => item.id),
      ["search", "chat", "explore", "live", "inbox", "admin", "my-journey", "settings"],
    );
    const owner = buildPrimaryNavItems({ role: "owner", isOwner: true });
    assert.deepEqual(
      owner.map((item) => item.id),
      ["search", "chat", "explore", "inbox", "admin", "my-journey", "settings"],
    );
    const withLive = buildPrimaryNavItems({
      role: "owner",
      isOwner: true,
      liveChannelsReady: true,
    });
    assert.deepEqual(
      withLive.map((item) => item.id),
      ["search", "chat", "explore", "live", "inbox", "admin", "my-journey", "settings"],
    );
    assert.equal(owner.at(-2).id, "my-journey");
    assert.equal(owner.at(-1).id, "settings");
  });

  it("hides Admin for members and places My Journey left of Settings", () => {
    const ids = primaryNavVisibleIds({ role: "member", isOwner: false });
    assert.deepEqual(ids, ["search", "chat", "explore", "inbox", "my-journey", "settings"]);
  });

  it("paints public peers while auth is unresolved and never includes Admin", () => {
    const unresolved = primaryNavVisibleIds({
      role: "owner",
      isOwner: true,
      multiUserEnabled: true,
      authReady: false,
    });
    assert.deepEqual(unresolved, [
      "search",
      "chat",
      "explore",
      "inbox",
      "my-journey",
      "settings",
    ]);
    assert.equal(unresolved.includes("admin"), false);
    assert.equal(unresolved.includes("live"), false);

    const unresolvedWithLive = primaryNavVisibleIds({
      role: "owner",
      isOwner: true,
      authReady: false,
      liveChannelsReady: true,
    });
    assert.deepEqual(unresolvedWithLive, [
      "search",
      "chat",
      "explore",
      "live",
      "inbox",
      "my-journey",
      "settings",
    ]);
    assert.equal(unresolvedWithLive.includes("admin"), false);

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

  it("legacy guest role sees the same peers as a member", () => {
    assert.deepEqual(
      primaryNavVisibleIds({ role: "guest" }),
      primaryNavVisibleIds({ role: "member" }),
    );
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
    const beforeAuth = buildPrimaryDrawerItems({ isOwner: true, authReady: false });
    assert.deepEqual(
      beforeAuth.map((item) => item.id),
      ["search", "chat", "explore", "inbox", "my-journey", "settings"],
    );
    assert.equal(beforeAuth.some((item) => item.id === "admin"), false);
  });

  it("keeps Live in the pending-auth peer set when this install already knows it", () => {
    const storage = new Map();
    const memory = {
      getItem: (key) => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    };
    globalThis.window = { __PROJECTIONIST_NAV__: { liveChannelsReady: true } };
    try {
      assert.equal(initialLiveChannelsReady(memory), true);
      assert.equal(memory.getItem(LIVE_NAV_READY_KEY), "1");
      const ids = primaryNavVisibleIds({
        role: "owner",
        isOwner: true,
        multiUserEnabled: true,
        authReady: false,
        liveChannelsReady: initialLiveChannelsReady(memory),
      });
      assert.deepEqual(ids, [
        "search",
        "chat",
        "explore",
        "live",
        "inbox",
        "my-journey",
        "settings",
      ]);
      assert.equal(ids.includes("admin"), false);
    } finally {
      delete globalThis.window;
    }
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
