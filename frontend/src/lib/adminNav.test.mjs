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
  it("lists core admin sections including Issues, Logs, Youth, and Taxonomy", () => {
    const ids = adminNavLinks().map((item) => item.id);
    assert.ok(ids.includes("overview"));
    assert.ok(ids.includes("logs"));
    assert.ok(ids.includes("issues"));
    assert.ok(ids.includes("youth"));
    assert.ok(ids.includes("taxonomy"));
    assert.equal(adminNavLinks().find((item) => item.id === "issues")?.badge, "openIssues");
    assert.equal(adminNavLinks().find((item) => item.id === "logs")?.to, "/admin/logs");
    assert.equal(adminNavLinks().find((item) => item.id === "tasks")?.label, "Tasks");
    assert.equal(
      adminNavLinks().find((item) => item.id === "taxonomy")?.label,
      "Library knowledge",
    );
    assert.equal(adminNavLinks().find((item) => item.id === "taxonomy")?.to, "/admin/taxonomy");
    assert.equal(adminNavLinks().find((item) => item.id === "mail")?.label, "Mail");
    assert.equal(adminNavLinks().find((item) => item.id === "usage")?.label, "Usage");
    assert.equal(adminNavLinks().find((item) => item.id === "usage")?.to, "/admin/usage");
    assert.equal(adminNavLinks().find((item) => item.id === "holidays")?.label, "Holidays");
    assert.equal(adminNavLinks().find((item) => item.id === "holidays")?.to, "/admin/holidays");
    assert.equal(adminNavLinks().length, 18);
  });

  it("groups the dense rail with Home / Household / Ops headings", () => {
    const headings = ADMIN_NAV.filter((item) => item.kind === "heading").map((item) => item.label);
    assert.deepEqual(headings, ["Home", "Household", "Ops"]);
    const groups = adminNavGroups();
    assert.equal(groups.length, 3);
    assert.deepEqual(
      groups.map((group) => group.label),
      ["Home", "Household", "Ops"],
    );
    assert.equal(
      groups.reduce((sum, group) => sum + group.links.length, 0),
      18,
    );
    assert.deepEqual(
      groups[0].links.map((item) => item.id),
      ["overview", "connections", "libraries"],
    );
    assert.equal(
      adminNavLinks().some((item) => item.id === "sync"),
      false,
      "Sync library lives on Libraries; Sync is not a nav item",
    );
    assert.ok(groups[2].links.some((item) => item.id === "taxonomy"));
  });

  it("detects /admin paths", () => {
    assert.equal(isAdminPath(ROUTES.admin), true);
    assert.equal(isAdminPath("/admin/overview"), true);
    assert.equal(isAdminPath("/admin/mail"), true);
    assert.equal(isAdminPath("/settings"), false);
    assert.equal(isAdminPath("/chat"), false);
    assert.equal(isAdminPath(""), false);
  });

  it("builds drawer items with stable test ids (including headings)", () => {
    const items = buildAdminDrawerItems();
    assert.equal(items.length, ADMIN_NAV.length);
    assert.equal(items[0].kind, "heading");
    assert.equal(items[0].id, "admin-heading-home");
    const overview = items.find((item) => item.id === "admin-overview");
    assert.equal(overview?.kind, "admin");
    assert.equal(overview?.testId, "app-nav-admin-overview");
    assert.equal(items.find((item) => item.id === "admin-issues")?.badge, "openIssues");
  });
});
