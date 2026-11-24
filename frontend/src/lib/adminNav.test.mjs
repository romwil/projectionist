import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.ts";
import {
  ADMIN_NAV,
  SINGLE_USER_ADMIN_LINK_IDS,
  adminNavGroups,
  adminNavLinks,
  buildAdminDrawerItems,
  isAdminPath,
} from "./adminNav.ts";

describe("adminNav", () => {
  it("lists core admin sections including Health, Logs, Youth, and Taxonomy", () => {
    const ids = adminNavLinks().map((item) => item.id);
    assert.ok(ids.includes("overview"));
    assert.ok(ids.includes("logs"));
    assert.ok(ids.includes("health"));
    assert.ok(ids.includes("youth"));
    assert.ok(ids.includes("taxonomy"));
    assert.equal(adminNavLinks().find((item) => item.id === "health")?.badge, "openIssues");
    assert.equal(adminNavLinks().find((item) => item.id === "health")?.to, "/admin/health");
    assert.equal(adminNavLinks().find((item) => item.id === "logs")?.to, "/admin/logs");
    assert.equal(adminNavLinks().find((item) => item.id === "tasks")?.label, "Tasks");
    assert.equal(
      adminNavLinks().find((item) => item.id === "taxonomy")?.label,
      "Library knowledge",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "taxonomy")?.to, "/admin/taxonomy");
    assert.equal(adminNavLinks().find((item) => item.id === "mail")?.label, "Mail");
    assert.equal(adminNavLinks().find((item) => item.id === "newsletters")?.label, "Newsletters");
    assert.equal(
      adminNavLinks().find((item) => item.id === "newsletters")?.to,
      "/admin/newsletters",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "holidays")?.label, "Holidays");
    assert.equal(adminNavLinks().find((item) => item.id === "holidays")?.to, "/admin/holidays");
    assert.equal(
      adminNavLinks().some((item) => item.id === "house" || item.to === "/admin/house"),
      false,
      "Admin → House is removed (the weekly letter lives in Newsletters)",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "lobby")?.label, "Lobby");
    assert.equal(adminNavLinks().find((item) => item.id === "lobby")?.to, "/admin/lobby");
    assert.equal(
      adminNavLinks().find((item) => item.id === "advanced")?.subtitle,
      "Integrations & keys",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "household")?.label, "Members");
    assert.equal(adminNavLinks().find((item) => item.id === "playback")?.label, "Playback");
    assert.equal(adminNavLinks().find((item) => item.id === "playback")?.to, "/admin/playback");
    assert.equal(
      adminNavLinks().some((item) => item.id === "dashboard" || item.id === "usage" || item.id === "issues"),
      false,
    );
    assert.equal(adminNavLinks().length, 19);
  });

  it("groups the rail as Overview / Setup / Household / Experience / Health / Advanced", () => {
    const headings = ADMIN_NAV.filter((item) => item.kind === "heading").map((item) => item.label);
    assert.deepEqual(headings, [
      "Overview",
      "Setup",
      "Household",
      "Experience",
      "Health",
      "Advanced",
    ]);
    const groups = adminNavGroups();
    assert.equal(groups.length, 6);
    assert.deepEqual(
      groups.map((group) => group.label),
      ["Overview", "Setup", "Household", "Experience", "Health", "Advanced"],
    );
    assert.equal(groups[0].hideHeading, true, "Overview group label is hidden in the rail");
    assert.ok(groups.slice(1).every((group) => group.hideHeading === false));
    assert.equal(
      groups.reduce((sum, group) => sum + group.links.length, 0),
      19,
    );
    assert.deepEqual(
      groups.map((group) => group.links.map((item) => item.id)),
      [
        ["overview"],
        ["connections", "libraries"],
        ["household", "playback", "access", "youth"],
        ["live-channels", "lobby", "holidays", "seerr"],
        ["tasks", "health", "taxonomy", "logs"],
        ["persona", "mail", "newsletters", "advanced"],
      ],
    );
    const advancedIds = groups[5].links.map((item) => item.id);
    assert.ok(
      advancedIds.indexOf("newsletters") === advancedIds.indexOf("mail") + 1,
      "Newsletters sits next to Mail in Advanced",
    );
    assert.equal(
      adminNavLinks().find((item) => item.id === "live-channels")?.label,
      "Live",
    );
    assert.equal(
      adminNavLinks().find((item) => item.id === "live-channels")?.to,
      "/admin/live-channels",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "household")?.to, "/admin/household");
    assert.equal(
      adminNavLinks().some((item) => item.id === "sync"),
      false,
      "Sync library lives on Libraries; Sync is not a nav item",
    );
  });

  it("detects /admin paths", () => {
    assert.equal(isAdminPath(ROUTES.admin), true);
    assert.equal(isAdminPath("/admin/overview"), true);
    assert.equal(isAdminPath("/admin/mail"), true);
    assert.equal(isAdminPath("/admin/health"), true);
    assert.equal(isAdminPath("/settings"), false);
    assert.equal(isAdminPath("/chat"), false);
    assert.equal(isAdminPath(""), false);
  });

  it("builds drawer items with stable test ids (including headings)", () => {
    const items = buildAdminDrawerItems();
    assert.equal(items.length, ADMIN_NAV.length);
    assert.equal(items[0].kind, "heading");
    assert.equal(items[0].id, "admin-heading-overview");
    const overview = items.find((item) => item.id === "admin-overview");
    assert.equal(overview?.kind, "admin");
    assert.equal(overview?.testId, "app-nav-admin-overview");
    assert.equal(items.find((item) => item.id === "admin-health")?.badge, "openIssues");
    assert.equal(
      items.find((item) => item.id === "admin-advanced")?.subtitle,
      "Integrations & keys",
    );
  });

  it("filters single-user admin to the essentials with Experience grouping", () => {
    const links = adminNavLinks({ multiUserEnabled: false });
    assert.equal(links.length, SINGLE_USER_ADMIN_LINK_IDS.length);
    assert.deepEqual(
      links.map((item) => item.id),
      SINGLE_USER_ADMIN_LINK_IDS,
    );
    assert.equal(links.some((item) => item.id === "household"), false);
    assert.equal(links.some((item) => item.id === "playback"), true);
    assert.equal(links.some((item) => item.id === "access"), false);
    assert.equal(links.some((item) => item.id === "youth"), false);
    assert.equal(links.some((item) => item.id === "mail"), false);
    assert.equal(links.some((item) => item.id === "seerr"), false);

    const groups = adminNavGroups({ multiUserEnabled: false });
    assert.deepEqual(
      groups.map((group) => group.label),
      ["Overview", "Setup", "Household", "Experience", "Health", "Advanced"],
    );
    assert.equal(groups[0].hideHeading, true);
    assert.deepEqual(
      groups.map((group) => group.links.map((item) => item.id)),
      [
        ["overview"],
        ["connections", "libraries"],
        ["playback"],
        ["lobby", "live-channels"],
        ["tasks", "logs"],
        ["persona", "advanced"],
      ],
    );
    assert.match(String(groups[3].subtitle || ""), /On the wall/i);
    assert.equal(links.length, 10);
    assert.equal(links.some((item) => item.id === "health"), false);
    assert.equal(links.some((item) => item.id === "taxonomy"), false);
  });

  it("keeps Seerr in single-user nav when seerr_enabled", () => {
    const links = adminNavLinks({ multiUserEnabled: false, seerrEnabled: true });
    assert.equal(links.length, SINGLE_USER_ADMIN_LINK_IDS.length + 1);
    assert.ok(links.some((item) => item.id === "seerr"));
    const experience = adminNavGroups({ multiUserEnabled: false, seerrEnabled: true }).find(
      (group) => group.id === "heading-experience",
    );
    assert.deepEqual(
      experience.links.map((item) => item.id),
      ["lobby", "live-channels", "seerr"],
    );
  });
});
