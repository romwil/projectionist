import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  tonightHabitChrome,
  tonightOneLiner,
  tonightReadySpotlight,
} from "./whatsOnTonight.js";
import {
  addToTonightQueue,
  clearTonightQueue,
  loadTonightQueue,
  removeFromTonightQueue,
  saveTonightQueue,
} from "./tonightQueue.js";
import { readAllStyles } from "./readStyles.mjs";

const styles = readAllStyles();

describe("tonightOneLiner", () => {
  it("uses youth-safe empty copy", () => {
    const line = tonightOneLiner({
      curatorName: "Scout",
      isYouth: true,
      ready: false,
      channels: [],
    });
    assert.match(line, /age-friendly/i);
    assert.doesNotMatch(line, /Plex/i);
  });

  it("names a sample title for adults", () => {
    const line = tonightOneLiner({
      curatorName: "Jefferson",
      presetId: "classic-curator",
      ready: true,
      channels: [{ nowTitle: "Heat", name: "Chaos" }],
    });
    assert.match(line, /Heat/);
    assert.match(line, /Jefferson/);
  });

  it("leans scout-y for enthusiastic-scout", () => {
    const line = tonightOneLiner({
      curatorName: "Scout",
      presetId: "enthusiastic-scout",
      ready: true,
      channels: [{ nowTitle: "Heat" }, { nowTitle: "Ronin" }],
    });
    assert.match(line, /tune|humming|Heat/i);
  });
});

describe("tonightHabitChrome", () => {
  it("differs for youth vs adult", () => {
    const youth = tonightHabitChrome({ isYouth: true });
    const adult = tonightHabitChrome({ isYouth: false });
    assert.match(youth.title, /for you/i);
    assert.match(adult.title, /tonight/i);
    assert.match(youth.meta, /Age-friendly/i);
  });
});

describe("tonightReadySpotlight", () => {
  it("keeps youth wording soft", () => {
    const spot = tonightReadySpotlight({
      isYouth: true,
      channelCount: 3,
      curatorName: "Scout",
    });
    assert.match(spot.body, /age-friendly/i);
  });
});

describe("tonightQueue", () => {
  it("adds, dedupes, and clears in sessionStorage", () => {
    clearTonightQueue();
    let q = addToTonightQueue({ title: "Heat", channelId: "ch-1" });
    assert.equal(q.length, 1);
    q = addToTonightQueue({ title: "Heat", channelId: "ch-1" }, q);
    assert.equal(q.length, 1);
    q = addToTonightQueue({ title: "Ronin", channelId: "ch-2" }, q);
    assert.equal(q.length, 2);
    q = removeFromTonightQueue(q[0].id, q);
    assert.equal(q.length, 1);
    saveTonightQueue(q);
    assert.equal(loadTonightQueue().length, 1);
    assert.equal(clearTonightQueue().length, 0);
  });
});

describe("whats-on-tonight styles", () => {
  it("defines habit surface styles", () => {
    assert.match(styles, /\.whats-on-tonight\b/);
    assert.match(styles, /\.tonight-queue\b/);
  });
});
