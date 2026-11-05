import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.ts";
import {
  initialLiveChannelsReady,
  liveChannelsReadyFromFeatures,
  LIVE_NAV_READY_KEY,
} from "./liveNavReady.ts";
import {
  PRIMARY_NAV_ITEMS,
  buildPrimaryBottomNavItems,
  buildPrimaryDrawerItems,
  buildPrimaryNavItems,
  isPrimaryNavActive,
  primaryNavVisibleIds,
  shouldHidePrimaryBottomNav,
} from "./primaryNav.ts";

describe("primaryNav", () => {
  it("orders peers Search → Chat → Explore → Live → Inbox → Admin → Settings", () => {
    assert.deepEqual(
      PRIMARY_NAV_ITEMS.map((item) => item.id),
      ["search", "chat", "explore", "live", "inbox", "admin", "settings"],
    );
    const owner = buildPrimaryNavItems({ role: "owner", isOwner: true });
    assert.deepEqual(
      owner.map((item) => item.id),
      ["search", "chat", "explore", "inbox", "admin", "settings"],
    );
    const withLive = buildPrimaryNavItems({
      role: "owner",
      isOwner: true,
      liveChannelsReady: true,
    });
    assert.deepEqual(
      withLive.map((item) => item.id),
      ["search", "chat", "explore", "live", "inbox", "admin", "settings"],
    );
    assert.equal(owner.at(-2).id, "admin");
    assert.equal(owner.at(-1).id, "settings");
  });

  it("hides Admin for members (BD-2: no My Journey peer)", () => {
    const ids = primaryNavVisibleIds({ role: "member", isOwner: false });
    assert.deepEqual(ids, ["search", "chat", "explore", "inbox", "settings"]);
    assert.equal(ids.includes("my-journey"), false);
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
      "settings",
    ]);

    const itemsUnresolved = buildPrimaryNavItems({
      role: "owner",
      isOwner: true,
      authReady: false,
    });
    assert.equal(itemsUnresolved.some((item) => item.id === "admin"), false);
  });

  it("shows Live for owner, member, and youth when ready without a Tunarr URL", () => {
    const features = {
      features: {
        live_channels_enabled: true,
        live_channels_ready: true,
      },
    };
    assert.equal(features.tunarr, undefined);
    assert.equal(liveChannelsReadyFromFeatures(features), true);
    const ready = liveChannelsReadyFromFeatures(features);
    const cases = [
      { role: "owner", isOwner: true, liveChannelsReady: ready },
      { role: "member", isOwner: false, liveChannelsReady: ready },
      { role: "member", isOwner: false, isYouth: true, liveChannelsReady: ready },
    ];
    for (const opts of cases) {
      const items = buildPrimaryNavItems(opts);
      assert.equal(items.some((item) => item.id === "live" && item.to === ROUTES.live), true);
      assert.equal(items.some((item) => item.id === "admin"), Boolean(opts.isOwner));
      const drawer = buildPrimaryDrawerItems(opts);
      assert.equal(drawer.some((item) => item.id === "live"), true);
    }
    const youth = buildPrimaryNavItems(cases[2]);
    assert.equal(youth.find((item) => item.id === "chat")?.label, "Ask");
    assert.equal(youth.find((item) => item.id === "explore")?.label, "Browse");
    assert.equal(youth.some((item) => item.id === "admin"), false);
  });

  it("youth sees Ask/Browse labels, never Admin or My Journey", () => {
    const items = buildPrimaryNavItems({
      role: "member",
      isOwner: false,
      isYouth: true,
    });
    assert.equal(items.find((i) => i.id === "chat")?.label, "Ask");
    assert.equal(items.find((i) => i.id === "explore")?.label, "Browse");
    assert.equal(items.some((i) => i.id === "admin"), false);
    assert.equal(items.some((i) => i.id === "my-journey"), false);
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
        "app-nav-settings",
      ],
    );
    assert.ok(owner.every((item) => item.kind === "primary" && item.label && item.to));
    const beforeAuth = buildPrimaryDrawerItems({ isOwner: true, authReady: false });
    assert.deepEqual(
      beforeAuth.map((item) => item.id),
      ["search", "chat", "explore", "inbox", "settings"],
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

describe("buildPrimaryBottomNavItems (UX-014)", () => {
  it("passes through the base 5-item member set unchanged", () => {
    const items = buildPrimaryBottomNavItems({ role: "member", isOwner: false });
    assert.deepEqual(items.map((item) => item.id), [
      "search",
      "chat",
      "explore",
      "inbox",
      "settings",
    ]);
  });

  it("drops Live and Admin first to stay at 5 for an owner with live channels", () => {
    const items = buildPrimaryBottomNavItems({
      role: "owner",
      isOwner: true,
      liveChannelsReady: true,
    });
    assert.equal(items.length, 5);
    assert.deepEqual(items.map((item) => item.id), [
      "search",
      "chat",
      "explore",
      "inbox",
      "settings",
    ]);
  });
});

describe("shouldHidePrimaryBottomNav (UX-014)", () => {
  it("hides over the player routes", () => {
    assert.equal(shouldHidePrimaryBottomNav({ pathname: "/watch/123" }), true);
    assert.equal(shouldHidePrimaryBottomNav({ pathname: "/watch/123/popout" }), true);
    assert.equal(shouldHidePrimaryBottomNav({ pathname: "/live/watch" }), true);
  });

  it("never paints on the sign-in, join, or setup doors (UX-011)", () => {
    for (const pathname of ["/login", "/login/", "/join", "/setup"]) {
      assert.equal(shouldHidePrimaryBottomNav({ pathname }), true, pathname);
    }
    assert.equal(shouldHidePrimaryBottomNav({ pathname: "/loginx" }), false);
  });

  it("stays visible on ordinary routes", () => {
    assert.equal(shouldHidePrimaryBottomNav({ pathname: "/explore" }), false);
    assert.equal(shouldHidePrimaryBottomNav({ pathname: "/live" }), false);
  });

  it("hides only when the composer is focused on iOS, not elsewhere", () => {
    assert.equal(
      shouldHidePrimaryBottomNav({ pathname: "/chat", composerFocused: true, isIos: true }),
      true,
    );
    assert.equal(
      shouldHidePrimaryBottomNav({ pathname: "/chat", composerFocused: true, isIos: false }),
      false,
    );
    assert.equal(
      shouldHidePrimaryBottomNav({ pathname: "/chat", composerFocused: false, isIos: true }),
      false,
    );
  });
});
