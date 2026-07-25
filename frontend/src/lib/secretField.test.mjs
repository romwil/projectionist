import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canToggleSecretVisibility,
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

describe("canToggleSecretVisibility", () => {
  it("hides Show when the API-redacted field is empty", () => {
    assert.equal(canToggleSecretVisibility(""), false);
    assert.equal(canToggleSecretVisibility(null), false);
    assert.equal(canToggleSecretVisibility(undefined), false);
  });

  it("allows Show only for a typed draft value", () => {
    assert.equal(canToggleSecretVisibility("sk-draft"), true);
    assert.equal(canToggleSecretVisibility("x"), true);
  });
});
