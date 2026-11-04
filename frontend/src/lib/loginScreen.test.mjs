import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  AUTH_METHOD_ORDER,
  LOGIN_PRODUCT_STATEMENT,
  loginDoorDecision,
  loginLede,
  plexAdvancedCopy,
  resolveAuthMethods,
} from "./loginScreen.ts";

describe("resolveAuthMethods", () => {
  it("puts Plex first even when local is listed first upstream", () => {
    assert.deepEqual(resolveAuthMethods(["local", "oidc", "plex"]), [
      "plex",
      "oidc",
      "local",
    ]);
  });

  it("drops unknown and empty methods", () => {
    assert.deepEqual(resolveAuthMethods(["plex", "", "password", "LOCAL"]), ["plex", "local"]);
  });

  it("returns an empty list when nothing is enabled", () => {
    assert.deepEqual(resolveAuthMethods(null), []);
    assert.deepEqual(resolveAuthMethods([]), []);
  });

  it("keeps the canonical order constant", () => {
    assert.deepEqual(AUTH_METHOD_ORDER, ["plex", "oidc", "local"]);
  });
});

describe("loginLede", () => {
  it("speaks to Plex-only households without multi-user jargon", () => {
    const lede = loginLede(["plex"]);
    assert.match(lede, /Plex account/i);
    assert.doesNotMatch(lede, /multi-user/i);
    assert.doesNotMatch(lede, /token/i);
  });

  it("keeps Plex as the suggested path when multiple methods exist", () => {
    const lede = loginLede(["local", "plex"]);
    assert.match(lede, /Plex/i);
    assert.doesNotMatch(lede, /multi-user/i);
  });

  it("stays generic when Plex is off", () => {
    const lede = loginLede(["local", "oidc"]);
    assert.doesNotMatch(lede, /Plex/i);
    assert.doesNotMatch(lede, /multi-user/i);
  });

  it("states what the product is before asking for sign-in (PRD-004)", () => {
    assert.match(LOGIN_PRODUCT_STATEMENT, /Projectionist is/i);
    for (const methods of [["plex"], ["local", "plex"], ["local", "oidc"]]) {
      assert.ok(loginLede(methods).startsWith(LOGIN_PRODUCT_STATEMENT));
    }
  });
});

describe("plexAdvancedCopy", () => {
  it("uses a discreet Advanced toggle when closed", () => {
    const copy = plexAdvancedCopy({ open: false });
    assert.equal(copy.toggleLabel, "Advanced");
    assert.doesNotMatch(copy.toggleLabel, /token/i);
  });

  it("exposes recovery labels only after open", () => {
    const copy = plexAdvancedCopy({ open: true });
    assert.equal(copy.toggleLabel, "Hide advanced");
    assert.match(copy.tokenHelp, /Recovery only/i);
    assert.match(copy.tokenHelp, /Sign in with Plex/i);
    assert.equal(copy.emptyError, "Paste a Plex token to continue.");
  });
});

describe("loginDoorDecision (UX-011)", () => {
  const household = { features: { multi_user_enabled: true } };

  it("sends a signed-in person to their page instead of the form", () => {
    assert.equal(loginDoorDecision({ features: household, me: { user: { id: "u1" } } }), "redirect");
  });

  it("shows the form only when household mode has no session", () => {
    assert.equal(loginDoorDecision({ features: household, me: null }), "form");
    assert.equal(loginDoorDecision({ features: household, me: {} }), "form");
  });

  it("leaves the door in single-owner mode and goes to setup on first run", () => {
    assert.equal(loginDoorDecision({ features: { features: { multi_user_enabled: false } } }), "redirect");
    assert.equal(
      loginDoorDecision({ features: { ...household, setup_state: "setup" }, me: { user: { id: "u1" } } }),
      "setup",
    );
  });
});
