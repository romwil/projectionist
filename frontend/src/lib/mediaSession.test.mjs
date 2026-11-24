import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clearPlaybackMediaSession,
  mediaSessionArtwork,
  mediaSessionMetadata,
  syncPlaybackMediaSession,
} from "./mediaSession.ts";

describe("media session", () => {
  it("keeps a relative poster on this origin and drops a huge or empty one", () => {
    assert.equal(
      mediaSessionArtwork("/api/library/art/movie/1", "http://household.local"),
      "http://household.local/api/library/art/movie/1",
    );
    assert.equal(
      mediaSessionArtwork("https://cdn.example/poster.jpg", "http://household.local"),
      "https://cdn.example/poster.jpg",
    );
    assert.equal(mediaSessionArtwork("", "http://household.local"), "");
    assert.equal(mediaSessionArtwork("x".repeat(2001), "http://household.local"), "");
  });

  it("publishes the title and wires play, pause, and seek", () => {
    const handlers = new Map();
    const positions = [];
    const target = {
      metadata: null,
      playbackState: "none",
      setActionHandler(name, handler) {
        handlers.set(name, handler);
      },
      setPositionState(state) {
        positions.push(state);
      },
    };
    const calls = [];
    globalThis.MediaMetadata = class MediaMetadata {
      constructor(data) {
        Object.assign(this, data);
      }
    };
    syncPlaybackMediaSession(
      target,
      {
        title: "The Conversation",
        artwork: "/api/library/art/movie/9",
        paused: false,
        duration: 120,
        position: 15,
        onPlay: () => calls.push("play"),
        onPause: () => calls.push("pause"),
        onSeek: (seconds) => calls.push(`seek:${seconds}`),
        onSkip: (delta) => calls.push(`skip:${delta}`),
      },
      "http://household.local",
    );
    assert.equal(target.metadata.title, "The Conversation");
    assert.equal(target.metadata.artwork[0].src, "http://household.local/api/library/art/movie/9");
    assert.equal(target.playbackState, "playing");
    assert.equal(positions[0].position, 15);
    handlers.get("play")();
    handlers.get("pause")();
    handlers.get("seekto")({ seekTime: 40 });
    handlers.get("seekforward")();
    assert.deepEqual(calls, ["play", "pause", "seek:40", "skip:10"]);
    assert.equal(handlers.has("nexttrack"), false);
    clearPlaybackMediaSession(target);
    assert.equal(target.metadata, null);
    assert.equal(target.playbackState, "none");
    assert.equal(handlers.get("play"), null);
  });

  it("omits artwork when the title has none", () => {
    assert.deepEqual(mediaSessionMetadata({ title: "Untitled" }).artwork, []);
  });
});
