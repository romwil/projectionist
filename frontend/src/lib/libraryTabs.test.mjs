import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_LIBRARY_TAB,
  libraryCollectionsDetailPath,
  libraryHubPath,
  libraryShelvesDetailPath,
  parseLibraryTab,
} from "./libraryTabs.js";

test("parseLibraryTab", () => {
  assert.equal(parseLibraryTab(new URLSearchParams()), DEFAULT_LIBRARY_TAB);
  assert.equal(parseLibraryTab(new URLSearchParams("tab=watchlist")), "watchlist");
});

test("libraryHubPath", () => {
  assert.equal(libraryHubPath(), "/library");
  assert.equal(libraryHubPath("watchlist"), "/library?tab=watchlist");
  assert.equal(libraryShelvesDetailPath("a b"), "/library/shelves/a%20b");
  assert.equal(libraryCollectionsDetailPath(1), "/library/collections/1");
});
