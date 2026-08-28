import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { adminNavLinks } from "./adminNav.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

describe("llm usage UI smoke", () => {
  it("exposes LLM usage under Health admin nav", () => {
    const health = adminNavLinks().find((item) => item.id === "health");
    assert.equal(health?.label, "Health");
    assert.equal(health?.to, "/admin/health");
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

  it("registers Health page with usage tab redirect", () => {
    const src = readFileSync(join(__dirname, "../main.jsx"), "utf8");
    assert.match(src, /HealthPage/);
    assert.match(src, /path="health"/);
    assert.match(src, /path="usage"/);
    assert.match(src, /tab=usage/);
  });
});
