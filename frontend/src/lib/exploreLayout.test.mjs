import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { readAllStyles } from "./readStyles.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const styles = readAllStyles();
const explorePage = readFileSync(join(here, "../pages/ExplorePage.jsx"), "utf8");

describe("explore and recommendations responsive layout", () => {
  it("contains explore page overflow and local poster-rail scrolling", () => {
    assert.match(styles, /\.explore-page\s*\{[^}]*overflow-x:\s*clip/s);
    assert.match(styles, /\.explore-card-rail\s*\{[^}]*max-width:\s*100%/s);
    assert.match(styles, /\.explore-card-rail\s*\{[^}]*overflow-x:\s*auto/s);
    assert.match(styles, /\.explore-motif-chips\s*\{[^}]*flex-wrap:\s*wrap/s);
    assert.match(styles, /\.explore-motif-chips-scroll\s*\{[^}]*max-height:/s);
    assert.match(styles, /\.explore-motif-chips-scroll\s*\{[^}]*overflow-y:\s*auto/s);
    assert.match(styles, /\.explore-motif-chip\s*\{[^}]*max-width:\s*100%/s);
    assert.match(styles, /\.explore-section\s*\{[^}]*min-width:\s*0/s);
  });

  it("keeps Explore controls visible inside the reading column", () => {
    assert.match(styles, /\.explore-section-toolbar\s*\{[^}]*width:\s*min\(var\(--reading-column-max/s);
    assert.match(styles, /\.explore-section-toolbar\s*\{[^}]*overflow:\s*visible/s);
    assert.match(styles, /\.explore-section-bulk\s*\{[^}]*flex-wrap:\s*wrap/s);
    assert.match(styles, /\.media-browse-filter-menu\s+>\s+summary\s*\{[^}]*white-space:\s*nowrap/s);
  });

  it("keeps poster hover actions as corner icons on the poster", () => {
    assert.match(styles, /\.explore-poster\s*\{[^}]*position:\s*relative/s);
    assert.match(
      styles,
      /\.explore-hover-icon-watch\s*\{[^}]*top:\s*50%;[^}]*left:\s*50%;[^}]*transform:\s*translate\(-50%,\s*-50%\)/s,
    );
    assert.match(styles, /\.explore-hover-icon-trailer\s*\{[^}]*right:/s);
    assert.match(styles, /\.explore-hover-icon-recommend\s*\{[^}]*bottom:/s);
    assert.doesNotMatch(styles, /\.explore-card-hover-actions\s*\{[^}]*bottom:\s*3\.4rem/s);
  });

  it("makes the recommendations viewport fill width instead of a left-heavy column track", () => {
    assert.match(
      styles,
      /\.viewport \.turnstyle-track\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit/s,
    );
    assert.match(styles, /\.viewport \.turnstyle-track\s*\{[^}]*grid-auto-flow:\s*row/s);
    assert.match(styles, /\.viewport \.title-card\s*\{[^}]*min-width:\s*0/s);
    assert.match(styles, /\.viewport \.title-card \.overview\s*\{[^}]*-webkit-line-clamp:\s*4/s);
  });

  it("keeps inbox recommendation cards from collapsing into the 64px poster track", () => {
    assert.match(
      styles,
      /\.recommendation-card\s*\{[^}]*grid-template-columns:\s*64px\s+minmax\(0,\s*1fr\)/s,
    );
    assert.match(
      styles,
      /\.recommendation-card--text-only\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s,
    );
    assert.match(styles, /\.recommendation-card-body\s*\{[^}]*min-width:\s*0/s);
    assert.match(styles, /\.recommendations-inbox\s*\{[^}]*min-width:\s*0/s);
  });

  it("places unfinished leftover runtime on Explore and Afterglow last", () => {
    assert.match(explorePage, /id="unfinished"/);
    assert.match(explorePage, /id="afterglow"/);
    assert.match(explorePage, /getExploreHub/);
    assert.match(explorePage, /"unfinished"/);
    assert.match(explorePage, /"afterglow"/);
    assert.match(explorePage, /title="Unfinished"/);
    assert.match(explorePage, /title="Afterglow"/);
    assert.match(explorePage, /Review while it's warm/);
    assert.doesNotMatch(explorePage, /id="tonight-table"/);
    assert.doesNotMatch(explorePage, /"tonight_table"/);
    assert.doesNotMatch(explorePage, /Tonight's table/);
    const unfinishedIdx = explorePage.indexOf('id="unfinished"');
    const afterglowIdx = explorePage.indexOf('id="afterglow"');
    const revisitIdx = explorePage.indexOf('id="revisit-these"');
    const seasonalIdx = explorePage.indexOf('id="seasonal-spotlight"');
    const pulseIdx = explorePage.indexOf('id="library-pulse"');
    assert.ok(unfinishedIdx > 0 && revisitIdx > unfinishedIdx);
    assert.ok(seasonalIdx > revisitIdx);
    assert.ok(afterglowIdx > seasonalIdx);
    assert.ok(pulseIdx > afterglowIdx);
    const unfinishedBlock = explorePage.slice(unfinishedIdx, revisitIdx);
    assert.match(unfinishedBlock, /title="Unfinished"/);
    assert.match(unfinishedBlock, /leftover_label/);
    assert.doesNotMatch(unfinishedBlock, /explore-section-subtitle/);
    const revisitBlock = explorePage.slice(revisitIdx, revisitIdx + 500);
    assert.match(revisitBlock, /title="Revisit These"/);
    assert.doesNotMatch(revisitBlock, /explore-section-subtitle/);
  });

  it("renders Explore destinations as navigation guides with the search", () => {
    assert.match(explorePage, /EXPLORE_RAIL_LIMIT/);
    assert.match(explorePage, /getExploreHub\(\{ limit: EXPLORE_RAIL_LIMIT \}\)/);
    assert.match(explorePage, /className="explore-library-entry"/);
    assert.match(explorePage, /<nav className="explore-hub-links" aria-label="Browse the library"/);
    assert.match(explorePage, /className="explore-hub-guide"/);
    assert.match(explorePage, /explore-hub-guide-line">Every film/);
    assert.match(explorePage, /explore-hub-guide-line">Shows and episodes/);
    assert.match(explorePage, /explore-hub-guide-line">Follow one title/);
    assert.match(explorePage, /explore-hub-guide-line">Browse keywords/);
    assert.match(explorePage, /data-testid="explore-hub-browse-movies"/);
    assert.match(explorePage, /data-testid="explore-hub-browse-tv"/);
    assert.match(explorePage, /data-testid="explore-hub-related-titles"/);
    assert.match(explorePage, /data-testid="explore-hub-tags"/);
    assert.doesNotMatch(explorePage, /explore-hub-links--compact/);
    assert.doesNotMatch(explorePage, /explore-hub-card/);
    assert.doesNotMatch(explorePage, /Page through every film/);
    assert.doesNotMatch(explorePage, /Fresh episodes first/);
    assert.doesNotMatch(explorePage, /Start with one title, follow its connections/);
    assert.doesNotMatch(explorePage, /Browse keyword tags across your full library/);
    assert.doesNotMatch(styles, /\.explore-hub-links--compact/);
    assert.match(styles, /\.explore-hub-links\s*\{[^}]*grid-template-columns:\s*repeat\(4,/s);
    assert.match(styles, /\.explore-hub-guide\s*\{[^}]*min-height:\s*var\(--tap-min\)/s);
    const guideRule = styles.match(/\.explore-hub-guide\s*\{[^}]*\}/s);
    assert.ok(guideRule);
    assert.doesNotMatch(guideRule[0], /999px/);
  });

  it("omits Live habits and Double Feature from Explore", () => {
    assert.doesNotMatch(explorePage, /WhatsOnTonightHabit/);
    assert.doesNotMatch(explorePage, /TonightDoubleFeatureHabit/);
    assert.doesNotMatch(explorePage, /liveWatchHref/);
    assert.doesNotMatch(explorePage, /anniversaryLiveStarter/);
    assert.doesNotMatch(styles, /\.tonight-double-feature\s*\{/);
  });

  it("loads Explore from the hub payload and surfaces episode arrivals", () => {
    assert.match(explorePage, /getExploreHub/);
    assert.match(explorePage, /id="recently-added-episodes"/);
    assert.match(explorePage, /Recently added episodes/);
  });

  it("paints the Explore shell instead of a full-page loader while auth settles", () => {
    const appShell = readFileSync(join(here, "../layouts/AppShell.jsx"), "utf8");
    assert.match(explorePage, /blockUntilAuth=\{false\}/);
    assert.match(appShell, /blockUntilAuth && !authReady/);
    assert.match(appShell, /login-lede">Loading…/);
    // The viewport loader stays available for other shells. Explore must not use it.
    assert.doesNotMatch(
      explorePage.slice(explorePage.indexOf("return (")),
      /app-shell-auth-loading|login-lede">Loading…/,
    );
  });

  it("does not render descriptive subtitles under hub rail headers", () => {
    const sectionFn = explorePage.slice(
      explorePage.indexOf("function ExploreSection("),
      explorePage.indexOf("function FeedRail("),
    );
    assert.match(sectionFn, /<h2>/);
    assert.doesNotMatch(sectionFn, /explore-section-subtitle/);
    assert.doesNotMatch(sectionFn, /subtitle/);
    assert.match(sectionFn, /explore-empty/);
    assert.doesNotMatch(explorePage, /className="explore-section-subtitle"/);
    assert.doesNotMatch(explorePage, /A daily rotating corner of your collection/);
    assert.doesNotMatch(explorePage, /A light seasonal turn through your library/);
    assert.doesNotMatch(explorePage, /A daily rotating filmography from your shelves/);
    assert.doesNotMatch(explorePage, /Pick up where you left off/);
    assert.doesNotMatch(explorePage, /Leftover runtime you can still finish/);
    assert.doesNotMatch(explorePage, /Still warm — a few questions while the credits fade/);
    assert.match(explorePage, /title="Continue Watching"/);
    assert.match(explorePage, /Genre"} in your library/);
    assert.match(explorePage, /explore-hub-guide-line">Every film/);
  });

  it("puts seasonal staff-pick notes and chat on Explore for members", () => {
    assert.match(explorePage, /SeasonalSpotlightRail/);
    assert.doesNotMatch(explorePage, /Staff picks from your library for this season/);
    assert.match(styles, /\.explore-seasonal-rail--chat-open/);
    assert.match(styles, /\.seasonal-pick-chat\s*\{/);
    assert.match(styles, /\.explore-seasonal-chat-btn/);
  });
});
