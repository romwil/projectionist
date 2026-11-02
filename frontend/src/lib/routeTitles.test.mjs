import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  documentTitleFor,
  episodePageName,
  pageTitleFor,
  routeNamesItself,
  titlePageName,
  withAppName,
} from "./routeTitles.ts";

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

describe("item page names (A11Y-003)", () => {
  it("names a loaded film with its year", () => {
    assert.equal(titlePageName({ title: "Alien", year: 1979 }), "Alien (1979)");
    assert.equal(withAppName(titlePageName({ title: "Alien", year: 1979 })), "Alien (1979) · Projectionist");
  });

  it("drops a missing or junk year and stays empty while loading", () => {
    assert.equal(titlePageName({ title: "Alien" }), "Alien");
    assert.equal(titlePageName({ title: "Alien", year: "n/a" }), "Alien");
    assert.equal(titlePageName(null), "");
  });

  it("names an episode by show and code", () => {
    assert.equal(episodePageName({ showTitle: "The Wire", episodeTitle: "The Buys", code: "S01E03" }), "The Wire S01E03");
    assert.equal(episodePageName({ episodeTitle: "The Buys", code: "S01E03" }), "The Buys");
  });

  it("only title and episode routes wait to name themselves", () => {
    assert.equal(routeNamesItself("/title/movie/348"), true);
    assert.equal(routeNamesItself("/title/episode/abc"), true);
    assert.equal(routeNamesItself("/explore"), false);
  });
});
