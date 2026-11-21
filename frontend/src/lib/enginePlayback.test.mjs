import assert from "node:assert/strict";
import test from "node:test";

import {
  browserPlaybackProfile,
  chooseWebPlayback,
  engineSessionForPlayer,
  playThroughProjectionist,
} from "./enginePlayback.ts";

test("the household switch defaults the web player to the Plex path", async () => {
  let engineCalls = 0;
  const played = await chooseWebPlayback({
    features: { features: { play_through_projectionist: false } },
    openEngine: async () => {
      engineCalls += 1;
      return { playable: true, master_url: "/engine", plan: "remux" };
    },
    startPlex: async () => ({ stream_url: "/plex", engine: false }),
  });
  assert.equal(engineCalls, 0);
  assert.equal(played.stream_url, "/plex");
  assert.equal(playThroughProjectionist(null), false);
});

test("a playable remux uses the engine master and keeps the Plex path for captions", async () => {
  const profile = browserPlaybackProfile((type) => type.includes("avc1") || type.includes("mp4a.40.2"));
  assert.deepEqual(profile.video.map((item) => item.codec), ["h264"]);
  assert.equal(profile.audio.includes("ac3"), false);

  const engine = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: true,
      master_url: "/api/playback/sessions/s/token/master.m3u8",
      plan: "remux",
      session_id: "s",
    }),
    startPlex: async () => {
      throw new Error("plex should not start");
    },
  });
  assert.equal(engine.engine, true);
  assert.equal(engine.stream_url, "/api/playback/sessions/s/token/master.m3u8");

  const fallback = await chooseWebPlayback({
    features: { features: { play_through_projectionist: true } },
    openEngine: async () => ({
      playable: false,
      master_url: "",
      plan: "plex-fallback",
      reason: "Captions stay on the Plex path until they are tracks in the playlist.",
    }),
    startPlex: async () => ({ stream_url: "/plex", engine: false }),
  });
  assert.equal(fallback.stream_url, "/plex");
  assert.equal(engineSessionForPlayer({ playable: false, plan: "audio", master_url: "" }), null);
});
