import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { personaChipLabel, personaDropdownLabel } from "./personaLabels.js";

describe("personaDropdownLabel", () => {
  it("formats nickname — name for builtins", () => {
    assert.equal(
      personaDropdownLabel({ name: "Academic Critic", nickname: "The Professor" }),
      "The Professor — Academic Critic",
    );
  });

  it("falls back to name when nickname missing", () => {
    assert.equal(personaDropdownLabel({ name: "My Custom" }), "My Custom");
  });
});

describe("personaChipLabel", () => {
  it("prefers nickname", () => {
    assert.equal(
      personaChipLabel({ name: "Enthusiastic Scout", nickname: "Spark" }),
      "Spark",
    );
  });

  it("falls back to name", () => {
    assert.equal(personaChipLabel({ name: "My Custom" }), "My Custom");
  });
});
