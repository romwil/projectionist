import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  placeTitleCtaMoreMenu,
  TITLE_CTA_COPY,
  TITLE_CTA_ICONS,
  TITLE_CTA_PHONE_OVERFLOW,
  TITLE_CTA_SECONDARY_ORDER,
  watchedCtaPresentation,
} from "./titleCta.js";

const stylesDir = join(dirname(fileURLToPath(import.meta.url)), "../styles");

describe("titleCta catalog", () => {
  it("locks secondary order Trailer → Review → Watched → Chat → Together → Add", () => {
    assert.deepEqual([...TITLE_CTA_SECONDARY_ORDER], [
      "trailer",
      "review",
      "watched",
      "chat",
      "watchTogether",
      "add",
    ]);
  });

  it("uses distinct Material Symbols for review vs chat", () => {
    assert.equal(TITLE_CTA_ICONS.play, "play_circle");
    assert.equal(TITLE_CTA_ICONS.trailer, "movie");
    assert.equal(TITLE_CTA_ICONS.review, "rate_review");
    assert.equal(TITLE_CTA_ICONS.chat, "forum");
    assert.notEqual(TITLE_CTA_ICONS.review, TITLE_CTA_ICONS.chat);
    assert.equal(TITLE_CTA_ICONS.more, "more_horiz");
    assert.equal(TITLE_CTA_ICONS.openInPlex, "open_in_new");
  });

  it("keeps short visible labels with longer tooltips", () => {
    assert.equal(TITLE_CTA_COPY.review.label, "Review");
    assert.equal(TITLE_CTA_COPY.review.tooltip, "Leave a review");
    assert.equal(TITLE_CTA_COPY.chat.label, "Chat");
    assert.equal(TITLE_CTA_COPY.chat.tooltip, "Chat about this");
    assert.equal(TITLE_CTA_COPY.watchTogether.label, "Together");
    assert.equal(TITLE_CTA_COPY.watchTogether.tooltip, "Watch together");
    assert.equal(TITLE_CTA_COPY.openInPlex.label, "Open in Plex");
  });

  it("collapses chat / together / add into More on phone", () => {
    assert.deepEqual([...TITLE_CTA_PHONE_OVERFLOW], ["chat", "watchTogether", "add"]);
  });

  it("presents watched toggle with short label + full tooltip", () => {
    assert.deepEqual(watchedCtaPresentation({ view_count: 0 }), {
      icon: "visibility",
      label: "Watched",
      tooltip: "Mark as watched",
    });
    assert.deepEqual(watchedCtaPresentation({ view_count: 2 }), {
      icon: "visibility_off",
      label: "Unwatched",
      tooltip: "Mark as unwatched",
    });
  });

  it("places More menu without negative viewport coords", () => {
    const style = placeTitleCtaMoreMenu(
      { top: 100, bottom: 140, left: 20, width: 44, height: 40 },
      { width: 200, height: 160 },
      { innerWidth: 390, innerHeight: 844 },
    );
    assert.equal(style.top, "148px");
    assert.equal(style.left, "20px");
  });

  it("portaled More CSS stacks above the title drawer panel", () => {
    const ctaCss = readFileSync(join(stylesDir, "09-title-detail-home.css"), "utf8");
    const delightCss = readFileSync(join(stylesDir, "10-explore-delight.css"), "utf8");
    const menuBlock = ctaCss.match(
      /\.title-detail-cta-menu,\s*\n\.title-detail-cta-menu--portal \{([\s\S]*?)\n\}/,
    )?.[1];
    const panelBlock = delightCss.match(
      /\.title-detail-drawer-panel,\s*\n\.title-detail-drawer-panel--modal \{([\s\S]*?)\n\}/,
    )?.[1];
    const menuZ = Number(menuBlock?.match(/z-index:\s*(\d+)/)?.[1]);
    const panelZ = Number(panelBlock?.match(/z-index:\s*(\d+)/)?.[1]);
    assert.ok(menuZ >= 1000, `expected portal menu z-index >= 1000, got ${menuZ}`);
    assert.ok(panelZ >= 90, `expected drawer panel z-index, got ${panelZ}`);
    assert.ok(menuZ > panelZ, `More menu z-index ${menuZ} must exceed drawer panel ${panelZ}`);
  });
});
