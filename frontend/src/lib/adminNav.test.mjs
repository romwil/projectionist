import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import {
  ADMIN_NAV,
  adminNavGroups,
  adminNavLinks,
  buildAdminDrawerItems,
  isAdminPath,
} from "./adminNav.js";

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
    assert.equal(adminNavLinks().find((item) => item.id === "lobby")?.label, "Lobby");
    assert.equal(adminNavLinks().find((item) => item.id === "lobby")?.to, "/admin/lobby");
    assert.equal(
      adminNavLinks().find((item) => item.id === "advanced")?.subtitle,
      "Integrations & keys",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "household")?.label, "Members");
    assert.equal(
      adminNavLinks().some((item) => item.id === "dashboard" || item.id === "usage" || item.id === "issues"),
      false,
    );
    assert.equal(adminNavLinks().length, 18);
  });

  it("groups the dense rail with Setup / Experience / Platform / Communications / System headings", () => {
    const headings = ADMIN_NAV.filter((item) => item.kind === "heading").map((item) => item.label);
    assert.deepEqual(headings, [
      "Setup",
      "Experience",
      "Platform",
      "Communications",
      "System",
    ]);
    const groups = adminNavGroups();
    assert.equal(groups.length, 5);
    assert.deepEqual(
      groups.map((group) => group.label),
      ["Setup", "Experience", "Platform", "Communications", "System"],
    );
    assert.equal(
      groups.reduce((sum, group) => sum + group.links.length, 0),
      18,
    );
    assert.deepEqual(
      groups[0].links.map((item) => item.id),
      ["overview", "connections", "libraries", "persona", "household"],
    );
    assert.deepEqual(
      groups[1].links.map((item) => item.id),
      ["live-channels", "lobby", "holidays", "seerr"],
    );
    assert.ok(groups[2].links.some((item) => item.id === "health"));
    assert.ok(groups[3].links.some((item) => item.id === "mail"));
    assert.ok(groups[3].links.some((item) => item.id === "newsletters"));
    const commsIds = groups[3].links.map((item) => item.id);
    assert.ok(
      commsIds.indexOf("newsletters") === commsIds.indexOf("mail") + 1,
      "Newsletters sits next to Mail in Communications",
    );
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
    assert.equal(items[0].id, "admin-heading-setup");
    const overview = items.find((item) => item.id === "admin-overview");
    assert.equal(overview?.kind, "admin");
    assert.equal(overview?.testId, "app-nav-admin-overview");
    assert.equal(items.find((item) => item.id === "admin-health")?.badge, "openIssues");
    assert.equal(
      items.find((item) => item.id === "admin-advanced")?.subtitle,
      "Integrations & keys",
    );
  });
});
