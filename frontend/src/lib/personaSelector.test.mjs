import assert from "node:assert/strict";
import { describe, it } from "node:test";

function filterPersonasByVisibility(personas, userId) {
  return personas.filter(
    (p) =>
      p.visibility === "builtin" ||
      p.visibility === "shared" ||
      (p.visibility === "private" && p.owner_user_id === userId),
  );
}

function groupPersonas(personas) {
  return {
    builtin: personas.filter((p) => p.visibility === "builtin"),
    shared: personas.filter((p) => p.visibility === "shared"),
    private: personas.filter((p) => p.visibility === "private"),
  };
}

function sortPersonas(personas) {
  const order = { builtin: 0, shared: 1, private: 2 };
  return [...personas].sort(
    (a, b) => (order[a.visibility] ?? 3) - (order[b.visibility] ?? 3) || a.name.localeCompare(b.name),
  );
}

const SAMPLE_PERSONAS = [
  { id: "classic-curator", name: "Classic Curator", visibility: "builtin", owner_user_id: null },
  { id: "blunt-archivist", name: "Blunt Archivist", visibility: "builtin", owner_user_id: null },
  { id: "custom-1", name: "My Custom", visibility: "shared", owner_user_id: "owner-1" },
  { id: "private-1", name: "Secret Persona", visibility: "private", owner_user_id: "user-2" },
  { id: "private-2", name: "My Private", visibility: "private", owner_user_id: "user-1" },
];

describe("filterPersonasByVisibility", () => {
  it("returns builtin and shared for any user", () => {
    const result = filterPersonasByVisibility(SAMPLE_PERSONAS, "user-1");
    const ids = result.map((p) => p.id);
    assert.ok(ids.includes("classic-curator"));
    assert.ok(ids.includes("custom-1"));
  });

  it("only returns own private personas", () => {
    const result = filterPersonasByVisibility(SAMPLE_PERSONAS, "user-1");
    const privateIds = result.filter((p) => p.visibility === "private").map((p) => p.id);
    assert.deepEqual(privateIds, ["private-2"]);
    assert.ok(!privateIds.includes("private-1"));
  });

  it("returns no private personas for unknown user", () => {
    const result = filterPersonasByVisibility(SAMPLE_PERSONAS, "unknown");
    assert.equal(result.filter((p) => p.visibility === "private").length, 0);
  });
});

describe("groupPersonas", () => {
  it("groups by visibility tier", () => {
    const groups = groupPersonas(SAMPLE_PERSONAS);
    assert.equal(groups.builtin.length, 2);
    assert.equal(groups.shared.length, 1);
    assert.equal(groups.private.length, 2);
  });
});

describe("sortPersonas", () => {
  it("sorts builtin first, then shared, then private, alphabetically within each", () => {
    const sorted = sortPersonas(SAMPLE_PERSONAS);
    assert.equal(sorted[0].visibility, "builtin");
    assert.equal(sorted[0].name, "Blunt Archivist");
    assert.equal(sorted[1].name, "Classic Curator");
    assert.equal(sorted[2].visibility, "shared");
    assert.equal(sorted[3].visibility, "private");
  });
});
