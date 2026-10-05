import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  HOME_OPTIONAL_SUMMARY,
  SEARCH_OPTIONAL_SUMMARY,
  chatHomeOptionalGroup,
  searchOptionalGroup,
} from "./optionalPageExtras.js";
import { readAllStyles } from "./readStyles.mjs";

function detailsTag(source, testId) {
  const match = source.match(new RegExp(`<details\\b[^>]*data-testid="${testId}"[^>]*>`));
  assert.ok(match, `missing <details data-testid="${testId}">`);
  return match[0];
}

describe("optional page extras", () => {
  it("starts closed for chat home and ignores a thread already in progress", () => {
    assert.deepEqual(chatHomeOptionalGroup({ showWelcome: true }), {
      show: true,
      startOpen: false,
    });
    assert.equal(chatHomeOptionalGroup({ showWelcome: false }).show, false);
    assert.equal(chatHomeOptionalGroup({}).show, false);
    assert.equal(chatHomeOptionalGroup({ showWelcome: "true" }).show, false);
    assert.equal(chatHomeOptionalGroup(null).show, false);
  });

  it("starts closed on the search route only when beyond-the-library material exists", () => {
    assert.deepEqual(
      searchOptionalGroup({ isSearchRoute: true, showBeyond: true }),
      { show: true, startOpen: false },
    );
    assert.equal(
      searchOptionalGroup({ isSearchRoute: true, beyondUnavailable: true }).show,
      true,
    );
    assert.equal(searchOptionalGroup({ isSearchRoute: true }).show, false);
    assert.equal(
      searchOptionalGroup({ isSearchRoute: false, showBeyond: true }).show,
      false,
    );
    assert.equal(
      searchOptionalGroup({ isSearchRoute: 1, showBeyond: true, beyondUnavailable: "yes" }).show,
      false,
    );
    assert.equal(searchOptionalGroup(undefined).show, false);
  });

  it("keeps chat home extras in one closed disclosure under the welcome", () => {
    const workspace = readFileSync(
      new URL("../components/ChatWorkspace.jsx", import.meta.url),
      "utf8",
    );
    const welcome = workspace.indexOf("<WelcomePanel");
    const extras = workspace.indexOf('data-testid="home-optional-extras"');
    const bento = workspace.indexOf('data-testid="home-bento"');
    const whisper = workspace.indexOf("<WhisperInboxLink");
    const shelf = workspace.indexOf('data-testid="holdable-shelf"');
    assert.ok(welcome > 0 && extras > welcome);
    assert.ok(bento > extras && whisper > extras && shelf > extras);
    const tag = detailsTag(workspace, "home-optional-extras");
    assert.doesNotMatch(tag, /\sopen(?:\s|=|>)/);
    assert.match(workspace, /HOME_OPTIONAL_SUMMARY/);
    assert.equal(HOME_OPTIONAL_SUMMARY, "More from home");
    const threadGlance = workspace.indexOf("!showWelcomePanel && libraryGlance");
    assert.ok(threadGlance > extras);
  });

  it("keeps search hits ahead of one closed beyond-the-library disclosure", () => {
    const page = readFileSync(
      new URL("../pages/LibraryBrowsePage.jsx", import.meta.url),
      "utf8",
    );
    const results = page.indexOf('data-testid="library-browse-results"');
    const extras = page.indexOf('data-testid="search-optional-beyond"');
    assert.ok(results > 0 && extras > results);
    const tag = detailsTag(page, "search-optional-beyond");
    assert.doesNotMatch(tag, /\sopen(?:\s|=|>)/);
    assert.match(page, /searchOptionalGroup\(/);
    assert.match(page, /SEARCH_OPTIONAL_SUMMARY/);
    assert.equal(SEARCH_OPTIONAL_SUMMARY, "Beyond your collection");
    assert.match(page, /data-testid="explore-beyond"/);
    assert.match(page, /data-testid="explore-beyond-unavailable"/);
  });

  it("hides closed disclosure children when those blocks set their own display", () => {
    const styles = readAllStyles();
    assert.match(
      styles,
      /\.optional-disclosure:not\(\[open\]\) > :not\(summary\)\s*\{[^}]*display:\s*none/s,
    );
  });
});
