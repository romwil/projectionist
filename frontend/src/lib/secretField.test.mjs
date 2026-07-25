import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canToggleSecretVisibility,
  isSecretConfigured,
  secretPlaceholder,
  seerrSecretPlaceholder,
} from "./secretField.js";

describe("secretPlaceholder", () => {
  it("prefers env source copy", () => {
    assert.equal(
      secretPlaceholder({ llm_api_key_source: "env", llm_api_key_set: true }, "llm_api_key"),
      "Configured via environment (.env)",
    );
  });

  it("shows keep-blank copy when set in settings", () => {
    assert.equal(
      secretPlaceholder({ llm_api_key_set: true }, "llm_api_key", "Required"),
      "Configured (leave blank to keep)",
    );
  });

  it("falls back when unset", () => {
    assert.equal(secretPlaceholder({}, "llm_api_key", "Required except for Ollama"), "Required except for Ollama");
  });
});

describe("seerrSecretPlaceholder", () => {
  it("uses nested api_key_set", () => {
    assert.equal(
      seerrSecretPlaceholder({ seerr: { api_key_set: true } }),
      "Configured (leave blank to keep)",
    );
    assert.equal(seerrSecretPlaceholder({ seerr: { api_key_set: false } }, "paste key"), "paste key");
  });
});

describe("isSecretConfigured", () => {
  it("reads top-level _set flags", () => {
    assert.equal(isSecretConfigured({ llm_api_key_set: true }, "llm_api_key"), true);
    assert.equal(isSecretConfigured({ plex_token_set: false }, "plex_token"), false);
    assert.equal(isSecretConfigured({}, "radarr_api_key"), false);
  });

  it("reads nested seerr.api_key_set", () => {
    assert.equal(isSecretConfigured({ seerr: { api_key_set: true } }, "seerr.api_key"), true);
    assert.equal(isSecretConfigured({ seerr: { api_key_set: false } }, "seerr.api_key"), false);
  });
});

describe("canToggleSecretVisibility", () => {
  it("hides Show when empty and not configured", () => {
    assert.equal(canToggleSecretVisibility(""), false);
    assert.equal(canToggleSecretVisibility(null), false);
    assert.equal(canToggleSecretVisibility(undefined), false);
    assert.equal(canToggleSecretVisibility("", { configured: false }), false);
  });

  it("allows Show for a typed draft value", () => {
    assert.equal(canToggleSecretVisibility("sk-draft"), true);
    assert.equal(canToggleSecretVisibility("x"), true);
  });

  it("allows Show when a stored secret is configured (reveal fetch)", () => {
    assert.equal(canToggleSecretVisibility("", { configured: true }), true);
    assert.equal(canToggleSecretVisibility(null, { configured: true }), true);
  });
});
