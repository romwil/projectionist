import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatLanguageName,
  languageFacetKey,
  normalizeLanguageCode,
} from "./languageNames.js";

describe("languageNames", () => {
  it("maps common ISO codes to display names", () => {
    assert.equal(formatLanguageName("hi"), "Hindi");
    assert.equal(formatLanguageName("HI"), "Hindi");
    assert.equal(formatLanguageName("en"), "English");
    assert.equal(formatLanguageName("ja"), "Japanese");
  });

  it("falls back to uppercase code when unknown", () => {
    assert.equal(formatLanguageName("xx"), "XX");
  });

  it("normalizes region subtags for facet keys", () => {
    assert.equal(normalizeLanguageCode("pt-BR"), "pt");
    assert.equal(languageFacetKey("HI"), "hi");
  });
});
