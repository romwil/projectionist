import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatLanguageName,
  isKnownLanguageCode,
  languageFacetKey,
  normalizeLanguageCode,
} from "./languageNames.ts";

describe("languageNames", () => {
  it("maps common ISO codes to display names", () => {
    assert.equal(formatLanguageName("hi"), "Hindi");
    assert.equal(formatLanguageName("HI"), "Hindi");
    assert.equal(formatLanguageName("en"), "English");
    assert.equal(formatLanguageName("ja"), "Japanese");
  });

  it("falls back to uppercase code when unknown", () => {
    assert.equal(formatLanguageName("xx"), "XX");
    assert.equal(isKnownLanguageCode("en"), true);
    assert.equal(isKnownLanguageCode("EN"), true);
    assert.equal(isKnownLanguageCode("xx"), false);
    assert.equal(isKnownLanguageCode(""), false);
  });

  it("normalizes region subtags for facet keys", () => {
    assert.equal(normalizeLanguageCode("pt-BR"), "pt");
    assert.equal(languageFacetKey("HI"), "hi");
  });
});
