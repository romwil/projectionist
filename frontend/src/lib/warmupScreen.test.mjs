import assert from "node:assert/strict";
import test from "node:test";

import {
  CHOICE_AFTER_MS,
  WARMUP_AFTER_MS,
  artFace,
  choicesDue,
  filmReadyForHandoff,
  honestStatus,
  jokeForHumor,
  nextWarmupLine,
  shouldPreloadDuringPreroll,
  warmupShouldShow,
} from "./warmupScreen.ts";

const lines = {
  general: ["rewinding. be kind.", "dusting off the good copy."],
  steps: {
    encoding_audio: ["teaching your surround sound to share."],
    remuxing: ["reading the label on the reel."],
  },
};

test("a quiet start shows the warm-up, and a picture or a preroll hides it", () => {
  assert.equal(warmupShouldShow({ elapsedMs: WARMUP_AFTER_MS - 1, hasPicture: false, prerollPlaying: false }), false);
  assert.equal(warmupShouldShow({ elapsedMs: WARMUP_AFTER_MS, hasPicture: false, prerollPlaying: false }), true);
  assert.equal(warmupShouldShow({ elapsedMs: 5_000, hasPicture: true, prerollPlaying: false }), false);
  assert.equal(warmupShouldShow({ elapsedMs: 5_000, hasPicture: false, prerollPlaying: true }), false);
});

test("lines follow the step, do not repeat, and dry humor stays quiet", () => {
  const used = new Set();
  const first = nextWarmupLine(lines, "encoding_audio", used);
  assert.equal(first, "teaching your surround sound to share.");
  used.add(first);
  assert.equal(nextWarmupLine(lines, "encoding_audio", used), "rewinding. be kind.");
  used.add("rewinding. be kind.");
  used.add("dusting off the good copy.");
  assert.equal(nextWarmupLine(lines, "encoding_audio", used), "");
  assert.equal(jokeForHumor("on", first, false), first);
  assert.equal(jokeForHumor("dry", first, false), "");
  assert.equal(jokeForHumor("on", first, true), "");
});

test("the status names the step and the 45 second choices wait for a picture", () => {
  assert.equal(honestStatus("encoding_audio", 6_200), "Preparing the sound for your speakers · 6 s");
  assert.equal(choicesDue({ elapsedMs: CHOICE_AFTER_MS - 1, hasPicture: false }), false);
  assert.equal(choicesDue({ elapsedMs: CHOICE_AFTER_MS, hasPicture: false }), true);
  assert.equal(choicesDue({ elapsedMs: CHOICE_AFTER_MS + 1, hasPicture: true }), false);
});

test("the film preloads in the last seconds of a ready preroll", () => {
  assert.equal(shouldPreloadDuringPreroll({ currentTime: 10, duration: 20, filmReady: true }), false);
  assert.equal(shouldPreloadDuringPreroll({ currentTime: 16, duration: 20, filmReady: true }), true);
  assert.equal(shouldPreloadDuringPreroll({ currentTime: 19, duration: 20, filmReady: false }), false);
  assert.equal(filmReadyForHandoff({ state: "preparing", engine: true }), false);
  assert.equal(filmReadyForHandoff({ state: "ready", engine: true }), true);
  assert.equal(filmReadyForHandoff({ plan: "library", state: "", engine: true }), true);
});

test("reduced motion holds one art face", () => {
  assert.equal(artFace(0, false), "backdrop");
  assert.equal(artFace(8_000, false), "poster");
  assert.equal(artFace(8_000, true), "backdrop");
});
