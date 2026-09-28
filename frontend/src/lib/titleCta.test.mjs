import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  placeTitleCtaMoreMenu,
  TITLE_CTA_COPY,
  TITLE_CTA_ICONS,
  TITLE_CTA_PHONE_OVERFLOW,
  TITLE_CTA_SECONDARY_ORDER,
  watchedCtaPresentation,
} from "./titleCta.js";

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
});
