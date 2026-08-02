import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  BROWSE_SEARCH_DEBOUNCE_MS,
  nextBrowseSearchQuery,
  normalizeBrowseSearchQuery,
  setBrowseSearchQueryParam,
} from "./progressiveBrowseSearch.js";

describe("progressiveBrowseSearch", () => {
  it("normalizes draft queries and exposes a light debounce budget", () => {
    assert.equal(normalizeBrowseSearchQuery("  blade  "), "blade");
    assert.equal(normalizeBrowseSearchQuery(""), "");
    assert.equal(normalizeBrowseSearchQuery(null), "");
    assert.ok(BROWSE_SEARCH_DEBOUNCE_MS >= 100 && BROWSE_SEARCH_DEBOUNCE_MS <= 400);
  });

  it("only emits a progressive update when draft differs from URL q", () => {
    assert.equal(nextBrowseSearchQuery("arrival", ""), "arrival");
    assert.equal(nextBrowseSearchQuery("  arrival  ", "arrival"), null);
    assert.equal(nextBrowseSearchQuery("arriva", "arrival"), "arriva");
    // Empty draft clears search → full browse.
    assert.equal(nextBrowseSearchQuery("", "arrival"), "");
    assert.equal(nextBrowseSearchQuery("   ", "arrival"), "");
    assert.equal(nextBrowseSearchQuery("", ""), null);
  });

  it("sets or clears the browse q param without inventing a second stack", () => {
    const withQ = setBrowseSearchQueryParam(new URLSearchParams("media_type=movie&offset=48"), "noir");
    assert.equal(withQ.get("q"), "noir");
    assert.equal(withQ.get("media_type"), "movie");

    const cleared = setBrowseSearchQueryParam(new URLSearchParams("q=noir&media_type=movie"), "  ");
    assert.equal(cleared.has("q"), false);
    assert.equal(cleared.get("media_type"), "movie");
  });

  it("wires progressive as-you-type search onto LibraryBrowsePage via existing q", () => {
    const page = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "..", "pages", "LibraryBrowsePage.jsx"),
      "utf8",
    );
    assert.match(page, /library-browse-search-input/);
    assert.match(page, /BROWSE_SEARCH_DEBOUNCE_MS/);
    assert.match(page, /nextBrowseSearchQuery/);
    assert.match(page, /setBrowseSearchQueryParam/);
    assert.match(page, /startTransition/);
    assert.match(page, /setDraftQ/);
    // Library filter still goes through queryLibrary + URL q — not a parallel stack.
    assert.match(page, /if \(q\) filters\.query = q/);
  });
});
