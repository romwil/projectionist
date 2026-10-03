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

  it("places unfinished leftover runtime and afterglow review rails on Explore", () => {
    assert.match(explorePage, /id="unfinished"/);
    assert.match(explorePage, /id="afterglow"/);
    assert.match(explorePage, /getExploreHub/);
    assert.match(explorePage, /"unfinished"/);
    assert.match(explorePage, /"afterglow"/);
    assert.match(explorePage, /Leftover runtime you can still finish/);
    assert.match(explorePage, /Still warm — a few questions while the credits fade/);
    assert.match(explorePage, /Review while it's warm/);
    const unfinishedIdx = explorePage.indexOf('id="unfinished"');
    const afterglowIdx = explorePage.indexOf('id="afterglow"');
    const revisitIdx = explorePage.indexOf('id="revisit-these"');
    assert.ok(unfinishedIdx > 0 && afterglowIdx > unfinishedIdx);
    assert.ok(revisitIdx > afterglowIdx);
    const unfinishedBlock = explorePage.slice(unfinishedIdx, afterglowIdx);
    assert.match(unfinishedBlock, /Leftover runtime you can still finish/);
    assert.doesNotMatch(unfinishedBlock, /haven.t touched in over two months/);
    const revisitBlock = explorePage.slice(revisitIdx, revisitIdx + 400);
    assert.match(revisitBlock, /haven.t touched in over two months/);
  });

  it("places tonight's table after continue watching and before leftover rails", () => {
    assert.match(explorePage, /id="tonight-table"/);
    assert.match(explorePage, /"tonight_table"/);
    assert.match(explorePage, /two unwatched seats and one comfort/);
    const continueIdx = explorePage.indexOf('id="continue-watching"');
    const tonightIdx = explorePage.indexOf('id="tonight-table"');
    const unfinishedIdx = explorePage.indexOf('id="unfinished"');
    const afterglowIdx = explorePage.indexOf('id="afterglow"');
    const revisitIdx = explorePage.indexOf('id="revisit-these"');
    assert.ok(continueIdx > 0 && tonightIdx > continueIdx);
    assert.ok(unfinishedIdx > tonightIdx);
    assert.ok(afterglowIdx > unfinishedIdx);
    assert.ok(revisitIdx > afterglowIdx);
    const tonightBlock = explorePage.slice(tonightIdx, unfinishedIdx);
    assert.match(tonightBlock, /not leftover or afterglow/);
    assert.doesNotMatch(tonightBlock, /Leftover runtime you can still finish/);
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

  it("puts seasonal staff-pick notes and chat on Explore for members", () => {
    assert.match(explorePage, /SeasonalSpotlightRail/);
    assert.match(explorePage, /Staff picks from your library for this season/);
    assert.match(styles, /\.explore-seasonal-rail--chat-open/);
    assert.match(styles, /\.seasonal-pick-chat\s*\{/);
    assert.match(styles, /\.explore-seasonal-chat-btn/);
  });
});
