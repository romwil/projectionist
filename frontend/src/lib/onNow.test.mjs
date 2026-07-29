import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatChannelLabel,
  formatOnNowLine,
  formatProgressHint,
  formatRemaining,
  normalizeOnNow,
} from "./onNow.js";
import { plexLiveTvUrl } from "./titleLinks.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

describe("normalizeOnNow", () => {
  it("returns null when disabled or missing", () => {
    assert.equal(normalizeOnNow(null), null);
    assert.equal(normalizeOnNow({ enabled: false, channels: [] }), null);
  });

  it("maps channel now/next into display rows", () => {
    const model = normalizeOnNow({
      enabled: true,
      ready: true,
      plex_hint: "Open Plex",
      channels: [
        {
          id: "ch-1",
          name: "Chaos Night",
          number: 100,
          now: {
            title: "Heat",
            content_rating: "R",
            percent: 45.2,
            seconds_elapsed: 900,
            seconds_remaining: 1080,
            started_at: 100,
            ends_at: 2080,
          },
          next: { title: "Ronin" },
        },
      ],
    });
    assert.equal(model.ready, true);
    assert.equal(model.channels.length, 1);
    assert.equal(model.channels[0].nowTitle, "Heat");
    assert.equal(model.channels[0].nextTitle, "Ronin");
    assert.equal(model.channels[0].percent, 45.2);
    assert.equal(model.channels[0].secondsRemaining, 1080);
    assert.equal(model.channels[0].progressHint, "45% · 18m left");
    assert.equal(model.plexHint, "Open Plex");
  });
});

describe("format helpers", () => {
  it("formats channel labels and on-now lines", () => {
    assert.equal(
      formatChannelLabel({ name: "Chaos", number: 100 }),
      "100 · Chaos",
    );
    assert.equal(
      formatOnNowLine({ nowTitle: "Heat", nextTitle: "Ronin" }),
      "Now: Heat · Next: Ronin",
    );
    assert.equal(formatOnNowLine({ nextTitle: "Soon" }), "Up next: Soon");
  });

  it("formats remaining time and progress hints", () => {
    assert.equal(formatRemaining(45), "45s left");
    assert.equal(formatRemaining(180), "3m left");
    assert.equal(formatRemaining(3900), "1h 5m left");
    assert.equal(formatProgressHint({ percent: 12.4, secondsRemaining: 120 }), "12% · 2m left");
    assert.equal(formatProgressHint({ isPaused: true }), "Paused");
  });
});

describe("plexLiveTvUrl", () => {
  it("builds a Live TV deep link", () => {
    assert.equal(plexLiveTvUrl(""), "https://app.plex.tv/desktop/#!/live-tv");
    assert.match(plexLiveTvUrl("abc"), /server\/abc\/live-tv/);
  });
});

describe("on-now theme-safe styles", () => {
  it("defines on-now panel styles", () => {
    assert.match(styles, /\.on-now-panel\b/);
    assert.match(styles, /\.dash-delight-row\b/);
    assert.match(styles, /\.on-now-progress-bar\b/);
  });
});
