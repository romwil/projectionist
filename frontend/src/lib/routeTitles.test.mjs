import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { documentTitleFor, pageTitleFor } from "./routeTitles.ts";

describe("routeTitles", () => {
  it("titles the home, chat, and help routes", () => {
    assert.equal(pageTitleFor("/"), "Projectionist");
    assert.equal(documentTitleFor("/"), "Projectionist");
    assert.equal(pageTitleFor("/chat"), "Chat");
    assert.equal(documentTitleFor("/help"), "Help · Projectionist");
  });

  it("prefers specific explore/library paths over their catch-alls", () => {
    assert.equal(pageTitleFor("/explore/tags"), "Tags");
    assert.equal(pageTitleFor("/explore"), "Explore");
    assert.equal(pageTitleFor("/explore/section/trending-now"), "Explore — Trending Now");
    assert.equal(pageTitleFor("/library/saved"), "Saved Pages");
    assert.equal(pageTitleFor("/library/saved/abc123"), "Saved Page");
    assert.equal(pageTitleFor("/library/shelves/abc123"), "Shelf");
    assert.equal(pageTitleFor("/library/collections/abc123"), "Collection");
    assert.equal(pageTitleFor("/library/some-legacy-page"), "Library");
  });

  it("titles dynamic admin/settings/watch routes distinctly", () => {
    assert.equal(pageTitleFor("/admin"), "Admin Overview");
    assert.equal(pageTitleFor("/admin/health"), "Health");
    assert.equal(pageTitleFor("/admin/mail"), "Mail");
    assert.equal(pageTitleFor("/admin/some-config-section"), "Some Config Section");
    assert.equal(pageTitleFor("/settings"), "Profile");
    assert.equal(pageTitleFor("/settings/voice"), "Voice");
    assert.equal(pageTitleFor("/watch/12345"), "Now Playing");
    assert.equal(pageTitleFor("/watch/12345/popout"), "Now Playing");
  });

  it("decodes and title-cases tag names", () => {
    assert.equal(pageTitleFor("/tag/feel-good"), "Tag — Feel Good");
  });

  it("falls back to Not Found for unmatched paths", () => {
    assert.equal(pageTitleFor("/this/does/not/exist"), "Not Found");
    assert.equal(documentTitleFor("/this/does/not/exist"), "Not Found · Projectionist");
  });
});
