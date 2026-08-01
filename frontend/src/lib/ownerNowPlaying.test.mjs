import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatHealthChip,
  normalizeOwnerNowPlaying,
} from "./ownerNowPlaying.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

describe("normalizeOwnerNowPlaying", () => {
  it("returns empty when status missing", () => {
    assert.deepEqual(normalizeOwnerNowPlaying(null), {
      enabled: false,
      engineUp: false,
      rows: [],
    });
  });

  it("maps now_playing rows with next wall time and health", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      broadcast: { sidecar_up: true },
      now_playing: [
        {
          id: "ch-1",
          name: "Chaos",
          number: 100,
          now_title: "Heat",
          percent: 45.2,
          seconds_remaining: 1080,
          next_title: "Ronin",
          next_start: 1_700_000_000,
          health: "streaming",
          stream_connections: 2,
          warning: "padded_stop",
          airing_why: "From the “Crime Spree” collection",
        },
      ],
    });
    assert.equal(model.enabled, true);
    assert.equal(model.rows.length, 1);
    assert.equal(model.rows[0].nowTitle, "Heat");
    assert.equal(model.rows[0].nextTitle, "Ronin");
    assert.equal(model.rows[0].healthLabel, "Streaming");
    assert.equal(model.rows[0].warning, "padded_stop");
    assert.equal(model.rows[0].airingWhy, "From the “Crime Spree” collection");
    assert.match(model.rows[0].progressHint, /45%/);
    assert.ok(model.rows[0].nextWall);
  });

  it("falls back to airing when now_playing absent", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      airing: [{ id: "a", name: "A", number: 1, title: "Only" }],
    });
    assert.equal(model.rows[0].nowTitle, "Only");
  });
});

describe("formatHealthChip", () => {
  it("labels known chips", () => {
    assert.equal(formatHealthChip("empty"), "Empty lineup");
    assert.equal(formatHealthChip("airing"), "Airing");
  });
});

describe("owner now-playing styles", () => {
  it("defines owner table styles", () => {
    assert.match(styles, /\.owner-now-playing\b/);
    assert.match(styles, /\.owner-now-playing-table\b/);
  });
});
