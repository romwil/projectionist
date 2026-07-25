import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ROUTES } from "./backNav.js";
import {
  ADMIN_NAV,
  buildAdminDrawerItems,
  isAdminPath,
} from "./adminNav.js";

describe("adminNav", () => {
  it("lists core admin sections including Issues and Youth review", () => {
    const ids = ADMIN_NAV.map((item) => item.id);
    assert.ok(ids.includes("overview"));
    assert.ok(ids.includes("issues"));
    assert.ok(ids.includes("youth"));
    assert.equal(ADMIN_NAV.find((item) => item.id === "issues")?.badge, "openIssues");
  });

  it("detects /admin paths", () => {
    assert.equal(isAdminPath(ROUTES.admin), true);
    assert.equal(isAdminPath("/admin/overview"), true);
    assert.equal(isAdminPath("/admin/mail"), true);
    assert.equal(isAdminPath("/settings"), false);
    assert.equal(isAdminPath("/chat"), false);
    assert.equal(isAdminPath(""), false);
  });

  it("builds drawer items with stable test ids", () => {
    const items = buildAdminDrawerItems();
    assert.equal(items.length, ADMIN_NAV.length);
    assert.equal(items[0].kind, "admin");
    assert.equal(items[0].id, "admin-overview");
    assert.equal(items[0].testId, "app-nav-admin-overview");
    assert.equal(items.find((item) => item.id === "admin-issues")?.badge, "openIssues");
  });
});
