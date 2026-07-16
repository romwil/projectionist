import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveActivePersonaId } from "./resolveActivePersona.js";

const PERSONAS = [
  { id: "classic", name: "Classic", is_default: false },
  { id: "blunt", name: "Blunt", is_default: true },
  { id: "custom", name: "Custom", is_default: false },
];

describe("resolveActivePersonaId", () => {
  it("keeps a valid current selection", () => {
    assert.equal(
      resolveActivePersonaId({
        activePersonaId: "custom",
        threadPersonaId: "classic",
        defaultPersonaId: "blunt",
        personas: PERSONAS,
      }),
      "custom",
    );
  });

  it("prefers thread persona when selection is empty", () => {
    assert.equal(
      resolveActivePersonaId({
        activePersonaId: null,
        threadPersonaId: "classic",
        defaultPersonaId: "blunt",
        personas: PERSONAS,
      }),
      "classic",
    );
  });

  it("falls back to defaultPersonaId then is_default", () => {
    assert.equal(
      resolveActivePersonaId({
        activePersonaId: null,
        threadPersonaId: null,
        defaultPersonaId: "blunt",
        personas: PERSONAS,
      }),
      "blunt",
    );
    assert.equal(
      resolveActivePersonaId({
        activePersonaId: null,
        threadPersonaId: "missing",
        defaultPersonaId: "also-missing",
        personas: PERSONAS,
      }),
      "blunt",
    );
  });

  it("falls back to first persona when nothing else matches", () => {
    assert.equal(
      resolveActivePersonaId({
        activePersonaId: null,
        personas: [{ id: "only", is_default: false }],
      }),
      "only",
    );
    assert.equal(resolveActivePersonaId({ personas: [] }), null);
  });

  it("ignores stale activePersonaId not in the list", () => {
    assert.equal(
      resolveActivePersonaId({
        activePersonaId: "deleted",
        defaultPersonaId: "blunt",
        personas: PERSONAS,
      }),
      "blunt",
    );
  });
});
