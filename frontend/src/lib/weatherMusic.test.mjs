import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createShuffleBag,
  drawFromBag,
  fadeVolume,
  MUSIC_BED_VOLUME,
  MUSIC_FADE_MS,
  WeatherMusicBed,
} from "./weatherMusic.ts";

function fakeAudio() {
  return {
    src: "",
    volume: 1,
    currentTime: 0,
    duration: 120,
    paused: true,
    plays: 0,
    play() {
      this.paused = false;
      this.plays += 1;
      return Promise.resolve();
    },
    pause() {
      this.paused = true;
    },
  };
}

function seeded(seed = 7) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

const tracks = (n) => Array.from({ length: n }, (_, i) => ({ id: `t${i}`, url: `/api/live/weather/muzak/t${i}` }));

function bed(n) {
  const made = [];
  const music = new WeatherMusicBed({
    tracks: tracks(n),
    rng: seeded(),
    createAudio: () => {
      const a = fakeAudio();
      made.push(a);
      return a;
    },
  });
  return { music, decks: made };
}

describe("weather music shuffle", () => {
  it("plays each of three files once before any repeats", () => {
    const ids = ["a", "b", "c"];
    let bag = createShuffleBag(ids, seeded());
    const drawn = [];
    for (let i = 0; i < 9; i += 1) {
      const next = drawFromBag(bag, ids, seeded(i + 3));
      bag = next.bag;
      drawn.push(next.id);
    }
    for (let round = 0; round < 3; round += 1) {
      assert.deepEqual([...drawn.slice(round * 3, round * 3 + 3)].sort(), ids);
    }
    for (let i = 1; i < drawn.length; i += 1) assert.notEqual(drawn[i], drawn[i - 1]);
  });

  it("fades linearly over the fade window", () => {
    assert.equal(fadeVolume(0, 1, 0), 0);
    assert.equal(fadeVolume(0, 1, MUSIC_FADE_MS / 2), 0.5);
    assert.equal(fadeVolume(1, 0, MUSIC_FADE_MS * 2), 0);
  });
});

describe("WeatherMusicBed", () => {
  it("fades to silence when a voice starts and fades in a different file when it ends", () => {
    const { music, decks } = bed(3);
    music.start(0);
    music.tick(MUSIC_FADE_MS);
    assert.equal(music.activeDeck.volume, MUSIC_BED_VOLUME);
    const first = music.history[0];

    music.voiceStart(2_000);
    music.tick(2_000 + MUSIC_FADE_MS / 2);
    assert.ok(decks[0].volume > 0 && decks[0].volume < MUSIC_BED_VOLUME, "mid-fade");
    music.tick(2_000 + MUSIC_FADE_MS);
    assert.equal(decks[0].volume, 0);
    assert.equal(decks[0].paused, true);
    assert.equal(music.isDucked, true);

    music.voiceEnd(10_000);
    assert.equal(music.history.length, 2);
    assert.notEqual(music.history[1], first);
    assert.equal(music.activeDeck, decks[1]);
    music.tick(10_000 + MUSIC_FADE_MS);
    assert.equal(decks[1].volume, MUSIC_BED_VOLUME);
    assert.equal(decks[1].paused, false);
  });

  it("fades a single file back into itself from the start", () => {
    const { music } = bed(1);
    music.start(0);
    music.tick(MUSIC_FADE_MS);
    music.activeDeck.currentTime = 40;
    music.voiceStart(1_000);
    music.tick(1_000 + MUSIC_FADE_MS);
    music.voiceEnd(5_000);
    assert.deepEqual(music.history, ["t0", "t0"]);
    assert.equal(music.activeDeck.currentTime, 0);
    assert.equal(music.activeDeck.src, "/api/live/weather/muzak/t0");
    music.tick(5_000 + MUSIC_FADE_MS);
    assert.equal(music.activeDeck.volume, MUSIC_BED_VOLUME);
  });

  it("crossfades to the next track when one ends between voiceovers", () => {
    const { music, decks } = bed(2);
    music.start(0);
    music.tick(MUSIC_FADE_MS);
    decks[0].currentTime = 119.5;
    music.tick(3_000);
    assert.equal(music.history.length, 2);
    assert.equal(music.activeDeck, decks[1]);
    music.tick(3_000 + MUSIC_FADE_MS);
    assert.equal(decks[0].volume, 0);
    assert.equal(decks[1].volume, MUSIC_BED_VOLUME);
  });

  it("plays nothing with an empty folder while the voice still runs", () => {
    const { music, decks } = bed(0);
    assert.equal(music.hasMusic, false);
    music.start(0);
    music.voiceStart(100);
    music.tick(100 + MUSIC_FADE_MS);
    music.voiceEnd(2_000);
    music.tick(5_000);
    assert.deepEqual(music.history, []);
    assert.equal(decks[0].plays + decks[1].plays, 0);
  });
});
