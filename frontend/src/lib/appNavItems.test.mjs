import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import { libraryHubPath } from "./libraryTabs.js";
import {
  APP_NAV_CORE_ITEMS,
  YOUTH_NAV_ITEMS,
  buildAppNavItems,
} from "./appNavItems.js";
import { ADMIN_NAV, adminNavLinks } from "./adminNav.js";
import { buildPrimaryNavItems } from "./primaryNav.js";

/** Ids between the Navigate heading and the next heading. */
function navigateBlock(items) {
  const start = items.findIndex((item) => item.id === "heading-navigate");
  if (start < 0) return [];
  const rest = items.slice(start + 1);
  const end = rest.findIndex((item) => item.kind === "heading");
  return (end < 0 ? rest : rest.slice(0, end)).map((item) => item.id);
}

/** Ids after the More heading. */
function moreBlock(items) {
  const start = items.findIndex((item) => item.id === "heading-more");
  if (start < 0) return [];
  return items.slice(start + 1).map((item) => item.id);
}

describe("buildAppNavItems", () => {
  it("mirrors the toolbar peers under Navigate, then secondary destinations under More", () => {
    const items = buildAppNavItems({ role: "owner", isOwner: true });
    assert.equal(items[0].id, "heading-navigate");
    assert.deepEqual(navigateBlock(items), [
      "search",
      "chat",
      "explore",
      "inbox",
      "admin",
      "my-journey",
      "settings",
    ]);
    assert.deepEqual(moreBlock(items), [
      "related-titles",
      "tags",
      "library",
      "help",
      "privacy",
      "about",
    ]);
  });

  it("gates the drawer on exactly the peers the toolbar shows", () => {
    for (const opts of [
      { role: "owner", isOwner: true },
      { role: "member", isOwner: false },
      { role: "member", isOwner: false, isYouth: true },
      { role: "guest" },
      { role: "owner", isOwner: false, multiUserEnabled: false },
    ]) {
      assert.deepEqual(
        navigateBlock(buildAppNavItems(opts)),
        buildPrimaryNavItems(opts).map((item) => item.id),
        `drawer/topbar peers drifted for ${JSON.stringify(opts)}`,
      );
    }
  });

  it("carries drawer labels (and youth wording) for the primary peers", () => {
    const member = buildAppNavItems({ role: "member" });
    assert.equal(member.find((item) => item.id === "my-journey")?.label, "My Journey");
    assert.equal(member.find((item) => item.id === "settings")?.testId, "app-nav-settings");

    const youth = buildAppNavItems({ role: "member", isYouth: true });
    assert.equal(youth.find((item) => item.id === "chat")?.label, "Ask");
    assert.equal(youth.find((item) => item.id === "explore")?.label, "Browse");
  });

  it("lists My Journey once — Navigate only, never repeated under More", () => {
    for (const opts of [
      { role: "owner", isOwner: true },
      { role: "member" },
      { role: "member", isYouth: true },
    ]) {
      const items = buildAppNavItems(opts);
      assert.equal(items.filter((item) => item.id === "my-journey").length, 1);
      assert.equal(moreBlock(items).includes("my-journey"), false);
    }
    assert.equal(
      APP_NAV_CORE_ITEMS.some((item) => item.id === "my-journey"),
      false,
    );
    assert.equal(
      YOUTH_NAV_ITEMS.some((item) => item.id === "my-journey"),
      false,
    );
  });

  it("never shows the Admin peer or section links to members", () => {
    const ids = buildAppNavItems({
      isOwner: false,
      role: "member",
      pathname: "/admin/overview",
    }).map((item) => item.id);
    assert.equal(ids.includes("admin"), false);
    assert.equal(ids.includes("heading-admin"), false);
    assert.equal(ids.includes("admin-overview"), false);
  });

  it("does not dump Admin section links into the drawer outside /admin", () => {
    const ids = buildAppNavItems({ isOwner: true, pathname: "/chat" }).map((item) => item.id);
    assert.equal(ids.includes("heading-admin"), false);
    assert.equal(ids.includes("admin-overview"), false);
    assert.equal(ids.includes("admin"), true);
    assert.equal(ids.includes("help"), true);
  });

  it("adds Admin section links on /admin/* without replacing Navigate", () => {
    const items = buildAppNavItems({ isOwner: true, pathname: "/admin/overview" });
    const ids = items.map((item) => item.id);
    assert.equal(ids[0], "heading-navigate");
    assert.deepEqual(navigateBlock(items), [
      "search",
      "chat",
      "explore",
      "inbox",
      "admin",
      "my-journey",
      "settings",
    ]);
    const adminIdx = ids.indexOf("heading-admin");
    assert.ok(adminIdx > 0);
    assert.equal(ids[adminIdx + 1], "admin-heading-setup");
    assert.ok(ids.includes("admin-overview"));
    assert.ok(ids.includes("admin-health"));
    assert.equal(
      items.filter((item) => item.kind === "admin").length,
      adminNavLinks().length,
    );
    assert.equal(
      items.filter((item) => String(item.id).startsWith("admin-heading-")).length,
      ADMIN_NAV.filter((item) => item.kind === "heading").length,
    );
    assert.ok(ids.indexOf("heading-more") > adminIdx);
    assert.deepEqual(moreBlock(items), [
      "related-titles",
      "tags",
      "library",
      "help",
      "privacy",
      "about",
    ]);
  });

  it("filters Admin drawer links for single-user installs", () => {
    const items = buildAppNavItems({
      isOwner: true,
      multiUserEnabled: false,
      pathname: "/admin/overview",
    });
    const adminLinks = items.filter((item) => item.kind === "admin");
    assert.equal(adminLinks.length, 9);
    assert.equal(adminLinks.some((item) => item.id === "admin-household"), false);
    assert.equal(adminLinks.some((item) => item.id === "admin-issues"), false);
    assert.ok(items.some((item) => item.id === "admin-heading-experience"));
  });

  it("shows no peers while auth is unresolved, so Admin never flashes", () => {
    const items = buildAppNavItems({
      isOwner: true,
      role: "owner",
      authReady: false,
      pathname: "/admin/overview",
    });
    const ids = items.map((item) => item.id);
    assert.equal(ids.includes("heading-navigate"), false);
    assert.equal(ids.includes("admin"), false);
    assert.equal(ids.includes("heading-admin"), false);
    assert.equal(ids[0], "heading-more");
  });

  it("keeps core browse destinations stable", () => {
    assert.equal(
      APP_NAV_CORE_ITEMS.find((item) => item.id === "related-titles")?.to,
      ROUTES.relatedTitles,
    );
    assert.equal(APP_NAV_CORE_ITEMS.find((item) => item.id === "watchlist"), undefined);
    assert.equal(APP_NAV_CORE_ITEMS.find((item) => item.id === "library")?.to, ROUTES.library);
  });

  it("keeps youth More reduced — My list plus Help, no adult tooling", () => {
    const items = buildAppNavItems({ isYouth: true, role: "member" });
    assert.deepEqual(moreBlock(items), ["watchlist", "help"]);
    assert.equal(items.find((item) => item.id === "watchlist")?.label, "My list");
    assert.equal(items.find((item) => item.id === "watchlist")?.to, libraryHubPath("watchlist"));
    assert.equal(navigateBlock(items).includes("admin"), false);
    assert.equal(navigateBlock(items).includes("my-journey"), true);
  });

  it("legacy guest role uses the member drawer, not a tour nav", () => {
    const items = buildAppNavItems({ role: "guest" });
    assert.deepEqual(navigateBlock(items), navigateBlock(buildAppNavItems({ role: "member" })));
    assert.deepEqual(moreBlock(items), moreBlock(buildAppNavItems({ role: "member" })));
    const ids = items.map((item) => item.id);
    assert.equal(ids.includes("tour"), false);
    assert.equal(ids.includes("inbox"), true);
    assert.equal(ids.includes("my-journey"), true);
  });
});
