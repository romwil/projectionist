import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  setupCommitHouseholdDomain,
  setupCommitInviteOnly,
  setupCommitTrustProxy,
  setupInviteOnlyDefault,
} from "./setupWizard.js";

describe("setupInviteOnlyDefault", () => {
  it("starts Private Household with invite-only off", () => {
    assert.equal(setupInviteOnlyDefault("private"), false);
  });

  it("forces Public Household invite-only on", () => {
    assert.equal(setupInviteOnlyDefault("public"), true);
  });
});

describe("setupCommitInviteOnly", () => {
  it("sends invite-only off for a default private commit", () => {
    assert.equal(setupCommitInviteOnly("private", false), false);
  });

  it("keeps an explicit private opt-in", () => {
    assert.equal(setupCommitInviteOnly("private", true), true);
  });

  it("always sends invite-only on for public, even if the toggle is false", () => {
    assert.equal(setupCommitInviteOnly("public", false), true);
    assert.equal(setupCommitInviteOnly("public", true), true);
  });
});

describe("setupCommitTrustProxy", () => {
  it("clears a leftover true when committing Private Household", () => {
    assert.equal(setupCommitTrustProxy("private", true), false);
    assert.equal(setupCommitTrustProxy("private", false), false);
  });

  it("keeps the Public Household TLS-proxy checkbox", () => {
    assert.equal(setupCommitTrustProxy("public", true), true);
    assert.equal(setupCommitTrustProxy("public", false), false);
  });
});

describe("setupCommitHouseholdDomain", () => {
  it("drops a stuck public domain on a private commit", () => {
    assert.equal(setupCommitHouseholdDomain("private", "movies.example.com"), "");
  });

  it("sends the trimmed public household domain", () => {
    assert.equal(setupCommitHouseholdDomain("public", " movies.example.com "), "movies.example.com");
  });
});
