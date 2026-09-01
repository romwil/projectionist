import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatHealthChip,
  isPlaceholderNowTitle,
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

  it("maps programmed rows with next wall time and health", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      broadcast: { sidecar_up: true },
      now_playing: [
        {
          id: "ch-1",
          name: "Chaos",
          number: 100,
          now_title: "Heat",
          now_kind: "program",
          percent: 45.2,
          seconds_remaining: 1080,
          next_title: "Ronin",
          next_start: 1_700_000_000,
          health: "airing",
          stream_connections: 2,
          lineup_programs: 12,
          warning: "padded_stop",
          airing_why: "From the “Crime Spree” collection",
        },
      ],
    });
    assert.equal(model.enabled, true);
    assert.equal(model.rows.length, 1);
    assert.equal(model.rows[0].nowTitle, "Heat");
    assert.equal(model.rows[0].nowKind, "program");
    assert.equal(model.rows[0].isEmpty, false);
    assert.equal(model.rows[0].nextTitle, "Ronin");
    assert.equal(model.rows[0].healthLabel, "Airing");
    assert.equal(model.rows[0].warning, "padded_stop");
    assert.equal(model.rows[0].airingWhy, "From the “Crime Spree” collection");
    assert.match(model.rows[0].progressHint, /45%/);
    assert.equal(model.rows[0].showProgress, true);
    assert.equal(model.rows[0].keepalive, true);
    assert.ok(model.rows[0].nextWall);
  });

  it("treats empty lineup as No lineup without fake progress", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      broadcast: { sidecar_up: true },
      now_playing: [
        {
          id: "ch-empty",
          name: "Mystery",
          number: 102,
          now_title: "Mystery · Up next",
          now_kind: "placeholder",
          percent: 10,
          seconds_remaining: 20000,
          next_title: "",
          health: "empty",
          stream_connections: 1,
          lineup_programs: 0,
        },
      ],
    });
    const row = model.rows[0];
    assert.equal(row.isEmpty, true);
    assert.equal(row.nowTitle, "No lineup");
    assert.equal(row.nextTitle, "No upcoming");
    assert.equal(row.progressHint, "");
    assert.equal(row.showProgress, false);
    assert.equal(row.percent, null);
    assert.equal(row.healthLabel, "Empty lineup");
    assert.equal(row.keepalive, true);
    assert.equal(row.nextWall, "");
  });

  it("labels a 100% / 0s slot as Slot ended without a fake bar", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      now_playing: [
        {
          id: "ch-end",
          name: "Noir",
          now_title: "Heat",
          now_kind: "program",
          percent: 100,
          seconds_remaining: 0,
          next_title: "Ronin",
          next_start: 1_700_000_100,
          health: "airing",
          lineup_programs: 9,
        },
      ],
    });
    const row = model.rows[0];
    assert.equal(row.slotEnded, true);
    assert.equal(row.progressHint, "Slot ended");
    assert.equal(row.showProgress, false);
    assert.equal(row.nowTitle, "Heat");
    assert.equal(row.nextTitle, "Ronin");
  });

  it("never labels keepalive as Streaming", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      now_playing: [
        {
          id: "ch-warm",
          name: "Chaos",
          now_title: "Heat",
          now_kind: "program",
          health: "streaming",
          stream_connections: 1,
          lineup_programs: 12,
          percent: 20,
          seconds_remaining: 600,
        },
      ],
    });
    assert.equal(model.rows[0].healthLabel, "Airing");
    assert.equal(model.rows[0].keepalive, true);
    assert.doesNotMatch(model.rows[0].healthLabel, /Streaming/i);
  });

  it("falls back to airing when now_playing absent", () => {
    const model = normalizeOwnerNowPlaying({
      live_channels_enabled: true,
      airing: [{ id: "a", name: "A", number: 1, title: "Only" }],
    });
    assert.equal(model.rows[0].nowTitle, "Only");
  });
});

describe("isPlaceholderNowTitle", () => {
  it("detects Tunarr Up next and flex labels", () => {
    assert.equal(isPlaceholderNowTitle("Mystery · Up next"), true);
    assert.equal(isPlaceholderNowTitle("flex"), true);
    assert.equal(isPlaceholderNowTitle("Heat"), false);
  });
});

describe("formatHealthChip", () => {
  it("labels known chips without Streaming", () => {
    assert.equal(formatHealthChip("empty"), "Empty lineup");
    assert.equal(formatHealthChip("airing"), "Airing");
    assert.equal(formatHealthChip("streaming"), "Airing");
  });
});

describe("owner now-playing styles", () => {
  it("defines owner table styles", () => {
    assert.match(styles, /\.owner-now-playing\b/);
    assert.match(styles, /\.owner-now-playing-table\b/);
    assert.match(styles, /\.owner-now-playing-keepalive\b/);
  });
});
