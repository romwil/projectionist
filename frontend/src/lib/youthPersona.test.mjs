import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { preferYouthFriendlyPersona } from "./youthPersona.js";

describe("preferYouthFriendlyPersona", () => {
  it("prefers Companion over Enthusiast", () => {
    const id = preferYouthFriendlyPersona(
      [
        { id: "enthusiast", name: "Enthusiast", visibility: "builtin" },
        { id: "companion", name: "Companion", visibility: "builtin" },
      ],
      "fallback",
    );
    assert.equal(id, "companion");
  });

  it("returns fallback when nothing friendly matches", () => {
    assert.equal(
      preferYouthFriendlyPersona([{ id: "scholar", name: "Scholar" }], "fallback"),
      "fallback",
    );
  });
});
