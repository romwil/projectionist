import assert from "node:assert/strict";
import test from "node:test";

import {
  browserPlaybackProfile,
  browserPlaybackProfileFromRuntime,
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
  const profile = browserPlaybackProfile(
    (type) => type.includes("avc1") || type.includes("mp4a.40.2"),
  );
  assert.deepEqual(
    profile.video.map((item) => item.codec),
    ["h264"],
  );
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

test("a full plan and an audio plan start library playback", async () => {
  for (const plan of ["full", "audio"]) {
    let plex = 0;
    const played = await chooseWebPlayback({
      features: { features: { play_through_projectionist: true } },
      openEngine: async () => ({
        playable: true,
        master_url: "/api/playback/sessions/s/token/master.m3u8",
        plan,
        session_id: "s",
        reason:
          plan === "full"
            ? "HEVC video is not playable on web (hevc level is above profile hevc 5.1)"
            : "H.264 video is playable on web; E-AC-3 audio is not, so the audio would be transcoded (eac3 not in profile)",
      }),
      startPlex: async () => {
        plex += 1;
        return { stream_url: "/plex", engine: false };
      },
    });
    assert.equal(plex, 1);
    assert.equal(played.stream_url, "/plex");
    assert.equal(played.engine, false);
  }
});

test("the profile lists HEVC, AV1, AC-3, E-AC-3, and 10-bit only when the check says yes", () => {
  const safari = browserPlaybackProfile(
    (type) =>
      type.includes("hvc1.1.6.L153.B0") ||
      type.includes("hvc1.2.4.L153.B0") ||
      type.includes("av01.0.13M.08") ||
      type.includes("ac-3") ||
      type.includes("ec-3") ||
      type.includes("avc1.640034"),
  );
  const hevc = safari.video.find((item) => item.codec === "hevc");
  assert.equal(hevc.max_level, "5.1");
  assert.equal(hevc.bit_depth, 10);
  assert.equal(
    safari.video.some((item) => item.codec === "av1" && item.bit_depth === 8),
    true,
  );
  assert.equal(safari.audio.includes("ac3"), true);
  assert.equal(safari.audio.includes("eac3"), true);
  assert.equal(safari.id, "web");
  assert.deepEqual(safari.containers, ["mp4", "hls-fmp4"]);

  const low = browserPlaybackProfile(
    (type) => type.includes("hvc1.1.6.L93.B0") || type.includes("avc1"),
  );
  const lowHevc = low.video.find((item) => item.codec === "hevc");
  assert.equal(lowHevc.max_level, "3.1");
  assert.equal(lowHevc.bit_depth, 8);

  const chrome = browserPlaybackProfile((type) => type.includes("avc1"));
  assert.equal(
    chrome.video.some((item) => item.codec === "hevc"),
    false,
  );
  assert.equal(
    chrome.video.some((item) => item.codec === "av1"),
    false,
  );
  assert.equal(chrome.audio.includes("eac3"), false);
  assert.equal(chrome.audio.includes("ac3"), false);
});

test("a 10-bit yes does not hide an 8-bit yes at a higher level", () => {
  const profile = browserPlaybackProfile(
    (type) => type.includes("hvc1.2.4.L93.B0") || type.includes("hvc1.1.6.L153.B0"),
  );
  const hevc = profile.video.filter((item) => item.codec === "hevc");
  assert.deepEqual(
    hevc.map((item) => ({ max_level: item.max_level, bit_depth: item.bit_depth })),
    [
      { max_level: "3.1", bit_depth: 10 },
      { max_level: "5.1", bit_depth: 8 },
    ],
  );
});

test("maybe on an unspecified hvc1 family does not claim Main 5.1", async () => {
  const family = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) =>
      type.includes('codecs="hvc1"') && !type.includes("hvc1.") ? "maybe" : "",
  });
  assert.equal(
    family.video.some((item) => item.codec === "hevc"),
    false,
  );

  const named = browserPlaybackProfile((type) => type.includes("hvc1.1.6.L153.B0"));
  const row = named.video.find((item) => item.codec === "hevc");
  assert.equal(row.max_level, "5.1");
  assert.equal(row.bit_depth, 8);

  const tenBit = browserPlaybackProfile((type) => type.includes("hvc1.2.4.L153.B0"));
  const deep = tenBit.video.find((item) => item.codec === "hevc");
  assert.equal(deep.max_level, "5.1");
  assert.equal(deep.bit_depth, 10);
});

test("canPlayType, MediaSource, and decodingInfo are the same profile", async () => {
  const safari = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) =>
      type.includes("hvc1.2.4.L153.B0") || type.includes("ec-3") || type.includes("avc1.640034")
        ? "probably"
        : "",
    isTypeSupported: () => false,
    decodingInfo: async () => ({ supported: false }),
  });
  assert.equal(safari.video.find((item) => item.codec === "hevc").bit_depth, 10);
  assert.equal(safari.audio.includes("eac3"), true);

  const chrome = await browserPlaybackProfileFromRuntime({
    canPlayType: (type) => (type.includes("avc1") ? "probably" : ""),
    isTypeSupported: (type) => type.includes("av01.0.13M.08"),
    decodingInfo: async (type) => ({ supported: type.includes("ac-3") }),
  });
  assert.equal(
    chrome.video.some((item) => item.codec === "hevc"),
    false,
  );
  assert.equal(
    chrome.video.some((item) => item.codec === "av1"),
    true,
  );
  assert.equal(chrome.audio.includes("ac3"), true);
  assert.equal(chrome.audio.includes("eac3"), false);
});
