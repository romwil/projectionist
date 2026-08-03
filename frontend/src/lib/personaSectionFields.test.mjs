import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "../components/PersonaSection.jsx"), "utf8");

describe("PersonaSection admin slider fields", () => {
  it("only declares slider keys supported by /api/persona PersonaMetrics", () => {
    const keys = [...source.matchAll(/key:\s*"([^"]+)"/g)].map((m) => m[1]);
    assert.deepEqual(keys.sort(), ["val_bro_prof", "val_dipl_snark", "val_pass_auto"].sort());
    assert.ok(!keys.includes("val_depth"), "val_depth is not on PersonaMetrics and would crash");
  });

  it("uses a defensive sliderValue helper instead of bare toFixed", () => {
    assert.ok(source.includes("function sliderValue"));
    assert.ok(source.includes("sliderValue(persona, key).toFixed(2)"));
    assert.ok(!source.includes("persona[key].toFixed(2)"));
  });

  it("does not expose behavioral or assembled prompt editing UI", () => {
    assert.ok(!source.includes("persona-edit-prompt"));
    assert.ok(!source.includes("persona-behavioral-preview"));
    assert.ok(!source.includes("persona-assembled-preview"));
    assert.ok(!source.includes("Edit prompt"));
    assert.ok(!source.includes("Save custom prompt"));
    assert.ok(!source.includes("Live assembled prompt"));
    assert.ok(source.includes("persona-capabilities"));
  });
});
