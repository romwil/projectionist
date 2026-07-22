import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveMemberShell, shellRootClass } from "./memberShell.js";

describe("resolveMemberShell", () => {
  it("stays default when multi-user is off", () => {
    assert.equal(resolveMemberShell({ role: "guest", isYouth: true, multiUserEnabled: false }), "default");
  });

  it("picks guest shell for guest role", () => {
    assert.equal(resolveMemberShell({ role: "guest", multiUserEnabled: true }), "guest");
  });

  it("picks youth shell for youth members", () => {
    assert.equal(resolveMemberShell({ role: "member", isYouth: true, multiUserEnabled: true }), "youth");
  });

  it("defaults for adult members", () => {
    assert.equal(resolveMemberShell({ role: "member", isYouth: false, multiUserEnabled: true }), "default");
  });
});

describe("shellRootClass", () => {
  it("adds youth and guest modifiers", () => {
    assert.match(shellRootClass("youth"), /app-root--youth/);
    assert.match(shellRootClass("guest"), /guest-shell/);
    assert.equal(shellRootClass("default"), "app-root");
  });
});
