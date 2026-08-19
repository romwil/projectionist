import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { guestDeepLinkBlocked, resolveMemberShell, shellRootClass } from "./memberShell.js";

describe("resolveMemberShell", () => {
  it("stays default when multi-user is off", () => {
    assert.equal(resolveMemberShell({ role: "guest", isYouth: true, multiUserEnabled: false }), "default");
  });

  it("maps a legacy guest role onto the default member shell", () => {
    assert.equal(resolveMemberShell({ role: "guest", multiUserEnabled: true }), "default");
  });

  it("picks youth shell for youth members", () => {
    assert.equal(resolveMemberShell({ role: "member", isYouth: true, multiUserEnabled: true }), "youth");
  });

  it("defaults for adult members", () => {
    assert.equal(resolveMemberShell({ role: "member", isYouth: false, multiUserEnabled: true }), "default");
  });
});

describe("guestDeepLinkBlocked", () => {
  it("never blocks — guests were migrated to members", () => {
    assert.equal(
      guestDeepLinkBlocked({ role: "guest", multiUserEnabled: true, authReady: true }),
      false,
    );
    assert.equal(
      guestDeepLinkBlocked({ role: "member", multiUserEnabled: true, authReady: true }),
      false,
    );
    assert.equal(
      guestDeepLinkBlocked({ role: "owner", multiUserEnabled: true, authReady: true }),
      false,
    );
  });
});

describe("shellRootClass", () => {
  it("adds youth modifiers and ignores legacy guest", () => {
    assert.match(shellRootClass("youth"), /app-root--youth/);
    assert.equal(shellRootClass("guest"), "app-root");
    assert.equal(shellRootClass("default"), "app-root");
  });
});
