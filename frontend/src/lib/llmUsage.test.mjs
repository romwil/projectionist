import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { adminNavLinks } from "./adminNav.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

describe("llm usage UI smoke", () => {
  it("exposes Usage under Ops admin nav", () => {
    const usage = adminNavLinks().find((item) => item.id === "usage");
    assert.equal(usage?.label, "Usage");
    assert.equal(usage?.to, "/admin/usage");
  });

  it("ships LlmUsagePage with filters and chart panels", () => {
    const src = readFileSync(join(__dirname, "../pages/LlmUsagePage.jsx"), "utf8");
    assert.match(src, /data-testid="llm-usage-page"/);
    assert.match(src, /data-testid="llm-usage-filters"/);
    assert.match(src, /getLlmUsage/);
    assert.match(src, /Tokens by day/);
    assert.match(src, /Calls by purpose/);
  });

  it("wires model catalog API into ConfigPage cheaper-tier picks", () => {
    const src = readFileSync(join(__dirname, "../pages/ConfigPage.jsx"), "utf8");
    assert.match(src, /getLlmModelCatalog/);
    assert.match(src, /llm-cheaper-picks/);
    assert.match(src, /renderModelPicker/);
  });

  it("registers /admin/usage route", () => {
    const src = readFileSync(join(__dirname, "../main.jsx"), "utf8");
    assert.match(src, /LlmUsagePage/);
    assert.match(src, /path="usage"/);
  });
});
